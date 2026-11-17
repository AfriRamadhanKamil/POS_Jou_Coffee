from flask import session
from flask_socketio import emit, join_room
from flask_jwt_extended import decode_token
from flask_jwt_extended.exceptions import JWTExtendedException

from app.auth.models import Device, User
from app.common.auth import ROLE_ADMIN, ROLE_KASIR, ROLE_SUPER_ADMIN
from app.extensions import db, socketio


@socketio.on("connect", namespace="/ws")
def handle_connect(auth=None):
    """Client connects to realtime orders namespace."""
    token = auth.get("token") if isinstance(auth, dict) else None
    if not isinstance(token, str) or not token:
        return False
    try:
        claims = decode_token(token)
    except JWTExtendedException:
        return False

    user_id = claims.get("sub")
    device_id = claims.get("device_id")
    user = db.session.get(User, user_id) if user_id else None
    device = Device.query.filter_by(user_id=user_id, device_id=device_id).first()
    if (
        not user
        or not user.is_active
        or user.deleted_at is not None
        or user.role != claims.get("role")
        or user.role not in (ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN)
        or not device
        or device.is_revoked
        or device.deleted_at is not None
    ):
        return False

    session["socket_device_id"] = device.device_id
    join_room("orders")
    emit("connected", {"message": "Terhubung ke notifikasi realtime POS Jou Coffee"})


@socketio.on("disconnect", namespace="/ws")
def handle_disconnect():
    session.pop("socket_device_id", None)


@socketio.on("join_device", namespace="/ws")
def handle_join_device(data):
    """Allow specific device to listen to targeted notifications."""
    device_id = data.get("device_id") if isinstance(data, dict) else None
    authenticated_device = session.get("socket_device_id")
    if device_id and device_id == authenticated_device:
        join_room(f"device_{device_id}")
        emit("device_joined", {"device_id": device_id})

