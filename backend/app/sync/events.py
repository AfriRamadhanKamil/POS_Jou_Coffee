import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.common.models import SyncBaseModel
from app.sync.models import SyncChange


_PENDING_SYNC_CHANGES = "jou_coffee_pending_sync_changes"
_EXCLUDED_FIELDS = {"password_hash", "pin_hash", "raw_webhook"}


def _serialize_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def serialize_model(instance):
    state = inspect(instance)
    return {
        attribute.key: _serialize_value(getattr(instance, attribute.key))
        for attribute in state.mapper.column_attrs
        if attribute.key not in _EXCLUDED_FIELDS
    }


def _record_model_changes(session, flush_context):
    new_objects = set(session.new)
    candidates = new_objects.union(session.dirty)
    pending = session.info.setdefault(_PENDING_SYNC_CHANGES, [])

    for instance in candidates:
        if not isinstance(instance, SyncBaseModel):
            continue

        state = inspect(instance)
        changed_fields = {
            attribute.key
            for attribute in state.mapper.column_attrs
            if state.attrs[attribute.key].history.has_changes()
        }
        if instance not in new_objects and (
            not changed_fields or changed_fields == {"server_version"}
        ):
            continue

        operation = "INSERT" if instance in new_objects else "UPDATE"
        deleted_at = state.attrs["deleted_at"].history
        if (
            operation == "UPDATE"
            and deleted_at.has_changes()
            and instance.deleted_at is not None
        ):
            operation = "DELETE"

        change = SyncChange(
            user_id=instance.created_by,
            entity_name=state.mapper.local_table.name,
            entity_id=instance.id,
            operation=operation,
            payload=json.dumps(serialize_model(instance), separators=(",", ":")),
            idempotency_key=(
                getattr(instance, "idempotency_key", None)
                if operation == "INSERT"
                else None
            ),
            device_id=instance.device_id
        )
        session.add(change)
        pending.append((instance, change))


def _assign_server_versions(session, flush_context):
    pending = session.info.get(_PENDING_SYNC_CHANGES, [])
    remaining = []
    for instance, change in pending:
        if change.server_version is None:
            remaining.append((instance, change))
            continue

        instance.server_version = change.server_version
        payload = json.loads(change.payload)
        payload["server_version"] = change.server_version
        change.payload = json.dumps(payload, separators=(",", ":"))

    session.info[_PENDING_SYNC_CHANGES] = remaining


def register_sync_events():
    if not event.contains(Session, "after_flush", _record_model_changes):
        event.listen(Session, "after_flush", _record_model_changes)
    if not event.contains(Session, "after_flush_postexec", _assign_server_versions):
        event.listen(Session, "after_flush_postexec", _assign_server_versions)
