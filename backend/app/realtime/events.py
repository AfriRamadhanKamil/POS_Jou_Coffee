from flask import request
from flask_socketio import emit, join_room, leave_room
from app.extensions import socketio


@socketio.on("connect", namespace="/ws")
def handle_connect():
    """Client connects to realtime orders namespace."""
    join_room("orders")
    emit("connected", {"message": "Terhubung ke notifikasi realtime POS Jou Coffee"})


@socketio.on("disconnect", namespace="/ws")
def handle_disconnect():
    leave_room("orders")


@socketio.on("join_device", namespace="/ws")
def handle_join_device(data):
    """Allow specific device to listen to targeted notifications."""
    device_id = data.get("device_id")
    if device_id:
        join_room(f"device_{device_id}")
        emit("device_joined", {"device_id": device_id})

