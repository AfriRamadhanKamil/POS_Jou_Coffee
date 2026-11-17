import json
from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import role_required, ALL_ROLES
from app.catalog.models import (
    Category, Menu, MenuVariant, ModifierGroup, Modifier,
    SalesChannel, MenuChannelPrice
)
from app.finance.models import ExpenseCategory
from app.inventory.models import Unit, Ingredient, Recipe, RecipeItem
from app.orders.models import Order, Table
from app.sync.events import serialize_model
from app.sync.models import SyncChange

sync_bp = Blueprint("sync", __name__, url_prefix="/api/v1/sync")
MAX_BATCH_SIZE = 500
MAX_PULL_LIMIT = 500
SERVER_MANAGED_MODELS = {
    "categories": Category,
    "menus": Menu,
    "menu_variants": MenuVariant,
    "modifier_groups": ModifierGroup,
    "modifiers": Modifier,
    "sales_channels": SalesChannel,
    "menu_channel_prices": MenuChannelPrice,
    "units": Unit,
    "ingredients": Ingredient,
    "recipes": Recipe,
    "recipe_items": RecipeItem,
    "tables": Table,
    "expense_categories": ExpenseCategory,
}


def _validate_batch_item(item, index, now):
    if not isinstance(item, dict):
        return None, f"Item {index} harus berupa objek"

    idempotency_key = item.get("idempotency_key")
    entity_name = item.get("entity")
    operation = item.get("operation", "INSERT")
    payload = item.get("payload")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        return None, f"Item {index} membutuhkan idempotency_key"
    if len(idempotency_key) > 64:
        return None, f"idempotency_key item {index} terlalu panjang"
    if not isinstance(entity_name, str) or not entity_name.strip() or len(entity_name) > 50:
        return None, f"Nama entity item {index} tidak valid"
    if not isinstance(operation, str):
        return None, f"Operation item {index} tidak valid"
    operation = operation.upper()
    if operation not in {"INSERT", "UPDATE", "DELETE"}:
        return None, f"Operation item {index} tidak didukung"
    if not isinstance(payload, dict):
        return None, f"Payload item {index} harus berupa objek"
    entity_id = payload.get("id")
    if not isinstance(entity_id, str) or not entity_id.strip() or len(entity_id) > 36:
        return None, f"Payload item {index} membutuhkan id yang valid"

    try:
        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False
        )
    except (TypeError, ValueError):
        return None, f"Payload item {index} tidak dapat diserialisasi"

    client_timestamp = item.get("client_timestamp")
    time_drift_detected = False
    if client_timestamp is not None:
        if not isinstance(client_timestamp, str):
            return None, f"client_timestamp item {index} tidak valid"
        try:
            client_time = datetime.fromisoformat(
                client_timestamp.replace("Z", "+00:00")
            )
        except ValueError:
            return None, f"client_timestamp item {index} tidak valid"
        if client_time.tzinfo is None:
            client_time = client_time.replace(tzinfo=timezone.utc)
        time_drift_detected = abs((now - client_time).total_seconds()) > 300

    return {
        "idempotency_key": idempotency_key.strip(),
        "entity_name": entity_name.strip(),
        "entity_id": entity_id.strip(),
        "operation": operation,
        "payload_json": payload_json,
        "time_drift_detected": time_drift_detected
    }, None


def _same_change(change, item):
    if (
        item["entity_name"] == "orders"
        and change.entity_name == "orders"
        and change.idempotency_key == item["idempotency_key"]
        and change.entity_id == item["entity_id"]
        and Order.query.filter_by(
            id=change.entity_id,
            idempotency_key=item["idempotency_key"]
        ).first()
    ):
        return True
    return (
        change.entity_name == item["entity_name"]
        and change.entity_id == item["entity_id"]
        and change.operation == item["operation"]
        and change.payload == item["payload_json"]
    )


def _push_result(item, change, duplicate):
    return {
        "idempotency_key": item["idempotency_key"],
        "status": "DUPLICATE" if duplicate else "SUCCESS",
        "duplicate": duplicate,
        "server_version": change.server_version,
        "time_drift_detected": change.time_drift_detected
    }


def _sync_push_response(results):
    return api_response({
        "processed": sum(result["status"] == "SUCCESS" for result in results),
        "duplicates": sum(result["status"] == "DUPLICATE" for result in results),
        "conflicts": sum(
            result["status"] in {
                "CONFLICT_SERVER_WINS",
                "SERVER_AUTHORITATIVE"
            }
            for result in results
        ),
        "items": results
    }, "Batch sync push berhasil")


def _server_wins_result(item, model):
    record = model.query.filter_by(id=item["entity_id"]).first()
    return {
        "idempotency_key": item["idempotency_key"],
        "status": "CONFLICT_SERVER_WINS" if record else "SERVER_AUTHORITATIVE",
        "duplicate": False,
        "server_version": record.server_version if record else None,
        "payload": serialize_model(record) if record else None
    }


def _first_order_insert_result(item):
    order = Order.query.filter_by(id=item["entity_id"]).first()
    if order:
        server_version = order.server_version
        payload = serialize_model(order)
    else:
        change = (
            SyncChange.query.filter_by(
                entity_name="orders",
                entity_id=item["entity_id"],
                operation="INSERT"
            )
            .order_by(SyncChange.server_version.asc())
            .first()
        )
        if not change:
            return None
        server_version = change.server_version
        payload = json.loads(change.payload)

    return {
        "idempotency_key": item["idempotency_key"],
        "status": "CONFLICT_SERVER_WINS",
        "duplicate": False,
        "server_version": server_version,
        "payload": payload
    }


@sync_bp.route("/push", methods=["POST"])
@jwt_required()
@role_required(*ALL_ROLES)
def sync_push():
    """
    Receives batch changes from client SQLite sync_outbox.
    Each item contains: entity, operation, payload, idempotency_key, device_id, client_timestamp.
    """
    claims = get_jwt()
    device_id = claims.get("device_id")
    user_id = get_jwt_identity()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Request sync harus berupa objek JSON", 400)
    batch = data.get("batch")
    if not isinstance(batch, list) or len(batch) > MAX_BATCH_SIZE:
        return error_response(
            f"Batch harus berupa daftar dengan maksimal {MAX_BATCH_SIZE} item",
            400
        )

    now = datetime.now(timezone.utc)
    normalized_batch = []
    signatures_by_key = {}
    for index, item in enumerate(batch):
        normalized, error = _validate_batch_item(item, index, now)
        if error:
            return error_response(error, 400)
        signature = (
            normalized["entity_name"],
            normalized["entity_id"],
            normalized["operation"],
            normalized["payload_json"]
        )
        key = normalized["idempotency_key"]
        if key in signatures_by_key and signatures_by_key[key] != signature:
            return error_response(
                "Satu idempotency_key tidak boleh digunakan untuk perubahan berbeda",
                409
            )
        signatures_by_key[key] = signature
        normalized_batch.append(normalized)

    keys = list(signatures_by_key)
    existing_changes = {}
    if keys:
        existing_changes = {
            change.idempotency_key: change
            for change in SyncChange.query.filter_by(user_id=user_id)
            .filter(SyncChange.idempotency_key.in_(keys))
            .all()
        }
    for item in normalized_batch:
        if item["entity_name"] in SERVER_MANAGED_MODELS:
            continue
        existing = existing_changes.get(item["idempotency_key"])
        if existing and not _same_change(existing, item):
            return error_response(
                "idempotency_key sudah digunakan untuk perubahan lain",
                409
            )

    results = []
    try:
        for item in normalized_batch:
            server_model = SERVER_MANAGED_MODELS.get(item["entity_name"])
            if server_model:
                results.append(_server_wins_result(item, server_model))
                continue

            change = existing_changes.get(item["idempotency_key"])
            duplicate = change is not None
            if (
                not duplicate
                and item["entity_name"] == "orders"
                and item["operation"] == "INSERT"
            ):
                conflict = _first_order_insert_result(item)
                if conflict:
                    results.append(conflict)
                    continue
            if not duplicate:
                change = SyncChange(
                    user_id=user_id,
                    entity_name=item["entity_name"],
                    entity_id=item["entity_id"],
                    operation=item["operation"],
                    payload=item["payload_json"],
                    idempotency_key=item["idempotency_key"],
                    time_drift_detected=item["time_drift_detected"],
                    device_id=device_id
                )
                db.session.add(change)
                db.session.flush()
                existing_changes[item["idempotency_key"]] = change
            results.append(_push_result(item, change, duplicate))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing_changes = {
            change.idempotency_key: change
            for change in SyncChange.query.filter_by(user_id=user_id)
            .filter(SyncChange.idempotency_key.in_(keys))
            .all()
        }
        if any(key not in existing_changes for key in keys):
            raise
        results = []
        for item in normalized_batch:
            if item["entity_name"] in SERVER_MANAGED_MODELS:
                results.append(_server_wins_result(
                    item,
                    SERVER_MANAGED_MODELS[item["entity_name"]]
                ))
                continue
            change = existing_changes[item["idempotency_key"]]
            if not _same_change(change, item):
                return error_response(
                    "idempotency_key sudah digunakan untuk perubahan lain",
                    409
                )
            results.append(_push_result(item, change, True))
    return _sync_push_response(results)


@sync_bp.route("/pull", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def sync_pull():
    """
    Pulls changes from server since last cursor (server_version).
    """
    try:
        cursor = int(request.args.get("cursor", 0))
        limit = int(request.args.get("limit", 200))
    except ValueError:
        return error_response("Cursor dan limit harus berupa bilangan bulat", 400)
    if cursor < 0:
        return error_response("Cursor tidak boleh negatif", 400)
    if limit < 1:
        return error_response("Limit harus lebih besar dari nol", 400)
    limit = min(limit, MAX_PULL_LIMIT)

    changes = SyncChange.query.filter(SyncChange.server_version > cursor).order_by(
        SyncChange.server_version.asc()
    ).limit(limit + 1).all()
    has_more = len(changes) > limit
    changes = changes[:limit]

    new_cursor = cursor
    items = []
    for c in changes:
        new_cursor = max(new_cursor, c.server_version)
        created_at = c.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        items.append({
            "server_version": c.server_version,
            "entity": c.entity_name,
            "entity_id": c.entity_id,
            "operation": c.operation,
            "payload": json.loads(c.payload),
            "created_at": created_at.isoformat()
        })

    return api_response({
        "cursor": new_cursor,
        "count": len(items),
        "has_more": has_more,
        "changes": items
    })

