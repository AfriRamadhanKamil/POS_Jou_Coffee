import json
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import (
    role_required, hash_password,
    ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN
)
from app.auth.models import User, Device, AuditLog

users_bp = Blueprint("users", __name__, url_prefix="/api/v1")


@users_bp.route("/users", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_users():
    claims = get_jwt()
    current_role = claims.get("role")

    query = User.query_active()
    if current_role == ROLE_ADMIN:
        # Admin can only see Kasir accounts
        query = query.filter_by(role=ROLE_KASIR)

    users = query.all()
    result = [{
        "id": u.id,
        "username": u.username,
        "name": u.name,
        "role": u.role,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None
    } for u in users]

    return api_response(result)


@users_bp.route("/users", methods=["POST"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def create_user():
    claims = get_jwt()
    current_role = claims.get("role")
    data = request.get_json() or {}

    username = data.get("username", "").strip()
    password = data.get("password", "")
    pin = data.get("pin")
    name = data.get("name", "").strip()
    role = data.get("role", ROLE_KASIR).strip()

    if not username or not password or not name:
        return error_response("Username, password, dan nama wajib diisi", 400)

    # Permission check on role creation
    if current_role == ROLE_ADMIN and role != ROLE_KASIR:
        return error_response("Admin hanya dapat mengelola akun Kasir", 403)

    # Enforce only 1 active Kasir account as stated in PRD
    if role == ROLE_KASIR:
        existing_kasir = User.query_active().filter_by(role=ROLE_KASIR).first()
        if existing_kasir:
            return error_response("Hanya diperbolehkan 1 akun Kasir aktif. Silakan edit akun Kasir yang sudah ada.", 400)

    if User.query.filter_by(username=username).first():
        return error_response("Username sudah terdaftar", 400)

    user = User(
        username=username,
        password_hash=hash_password(password),
        pin_hash=hash_password(str(pin)) if pin else None,
        name=name,
        role=role,
        is_active=True
    )
    db.session.add(user)
    db.session.commit()

    return api_response({
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role
    }, "User berhasil dibuat", 201)


@users_bp.route("/users/<user_id>", methods=["PATCH"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def update_user(user_id):
    claims = get_jwt()
    current_role = claims.get("role")

    user = User.query.get(user_id)
    if not user or user.deleted_at is not None:
        return error_response("User tidak ditemukan", 404)

    if current_role == ROLE_ADMIN and user.role != ROLE_KASIR:
        return error_response("Admin hanya dapat mengedit akun Kasir", 403)

    data = request.get_json() or {}
    if "name" in data:
        user.name = data["name"].strip()
    if "password" in data and data["password"]:
        user.password_hash = hash_password(data["password"])
    if "pin" in data and data["pin"]:
        user.pin_hash = hash_password(str(data["pin"]))
    if "is_active" in data:
        user.is_active = bool(data["is_active"])

    db.session.commit()
    return api_response({"id": user.id, "username": user.username, "name": user.name}, "User berhasil diperbarui")


@users_bp.route("/users/<user_id>", methods=["DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def delete_user(user_id):
    claims = get_jwt()
    current_role = claims.get("role")

    user = User.query.get(user_id)
    if not user or user.deleted_at is not None:
        return error_response("User tidak ditemukan", 404)

    if current_role == ROLE_ADMIN and user.role != ROLE_KASIR:
        return error_response("Admin hanya dapat menghapus akun Kasir", 403)

    user.soft_delete()
    db.session.commit()
    return api_response(None, "User berhasil dinonaktifkan")


@users_bp.route("/devices", methods=["GET"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def list_devices():
    devices = Device.query.all()
    result = [{
        "id": d.id,
        "user_id": d.user_id,
        "user_name": d.user.name if d.user else None,
        "device_id": d.device_id,
        "device_name": d.device_name,
        "is_revoked": d.is_revoked,
        "last_login_at": d.last_login_at.isoformat() if d.last_login_at else None
    } for d in devices]
    return api_response(result)


@users_bp.route("/devices/<device_id>", methods=["DELETE"])
@jwt_required()
@role_required(ROLE_ADMIN, ROLE_SUPER_ADMIN)
def revoke_device(device_id):
    """Revoke a registered device (e.g. lost phone)."""
    device = Device.query.filter((Device.id == device_id) | (Device.device_id == device_id)).first()
    if not device:
        return error_response("Perangkat tidak ditemukan", 404)

    device.is_revoked = True
    db.session.commit()
    return api_response(None, f"Perangkat {device.device_name or device.device_id} berhasil dicabut")


@users_bp.route("/audit-logs", methods=["GET"])
@jwt_required()
@role_required(ROLE_SUPER_ADMIN)
def list_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    result = [{
        "id": l.id,
        "user_id": l.user_id,
        "action": l.action,
        "entity": l.entity,
        "entity_id": l.entity_id,
        "old_values": l.old_values,
        "new_values": l.new_values,
        "ip_address": l.ip_address,
        "created_at": l.created_at.isoformat() if l.created_at else None
    } for l in logs]
    return api_response(result)
