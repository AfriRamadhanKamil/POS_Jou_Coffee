import json
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import role_required, ALL_ROLES
from app.sync.models import SyncChange

sync_bp = Blueprint("sync", __name__, url_prefix="/api/v1/sync")


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
    data = request.get_json() or {}
    batch = data.get("batch", [])

    results = []
    now = datetime.now(timezone.utc)

    for item in batch:
        idempotency_key = item.get("idempotency_key")
        entity_name = item.get("entity")
        operation = item.get("operation", "INSERT")
        payload = item.get("payload", {})
        client_timestamp_str = item.get("client_timestamp")

        # Time drift detection: flag if difference > 5 minutes
        time_drift_flag = False
        if client_timestamp_str:
            try:
                client_time = datetime.fromisoformat(client_timestamp_str.replace("Z", "+00:00"))
                if abs((now - client_time).total_seconds()) > 300:
                    time_drift_flag = True
            except Exception:
                pass

        # Record in sync_changes log table (server_version auto-increments)
        change_log = SyncChange(
            entity_name=entity_name,
            entity_id=payload.get("id", ""),
            operation=operation,
            payload=json.dumps(payload),
            device_id=device_id
        )
        db.session.add(change_log)
        db.session.flush()

        results.append({
            "idempotency_key": idempotency_key,
            "status": "SUCCESS",
            "server_version": change_log.server_version,
            "time_drift_detected": time_drift_flag
        })

    db.session.commit()
    return api_response({"processed": len(results), "items": results}, "Batch sync push berhasil")


@sync_bp.route("/pull", methods=["GET"])
@jwt_required()
@role_required(*ALL_ROLES)
def sync_pull():
    """
    Pulls changes from server since last cursor (server_version).
    """
    try:
        cursor = int(request.args.get("cursor", 0))
    except ValueError:
        cursor = 0

    limit = min(int(request.args.get("limit", 200)), 500)

    changes = SyncChange.query.filter(SyncChange.server_version > cursor).order_by(
        SyncChange.server_version.asc()
    ).limit(limit).all()

    new_cursor = cursor
    items = []
    for c in changes:
        new_cursor = max(new_cursor, c.server_version)
        items.append({
            "server_version": c.server_version,
            "entity": c.entity_name,
            "entity_id": c.entity_id,
            "operation": c.operation,
            "payload": json.loads(c.payload),
            "created_at": c.created_at.isoformat()
        })

    return api_response({
        "cursor": new_cursor,
        "count": len(items),
        "has_more": len(items) == limit,
        "changes": items
    })
