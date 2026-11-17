from datetime import datetime, timezone
from flask import Blueprint, request, current_app
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from app.extensions import limiter
from itsdangerous import URLSafeTimedSerializer
from app.extensions import db
from app.common.response import api_response, error_response
from app.common.auth import verify_password, hash_password, ROLE_KASIR
from app.auth.models import User, Device, AuditLog

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/login", methods=["POST"])
@limiter.limit(lambda: current_app.config["AUTH_LOGIN_RATE_LIMIT"])
def login():
    """
    Login with username and password or PIN.
    Requires device_id in request body.
    Enforces active device limit for Kasir.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Format login tidak valid", 400)
    username = data.get("username", "")
    password = data.get("password", "")
    pin = str(data.get("pin") or "").strip()
    device_id = data.get("device_id", "")
    device_name = data.get("device_name", "Device")

    if not isinstance(username, str) or not isinstance(device_id, str):
        return error_response("Username dan device_id harus berupa teks", 400)
    username = username.strip()
    device_id = device_id.strip()
    if not username or not device_id:
        return error_response("Username dan device_id wajib diisi", 400)
    if not isinstance(device_name, str):
        return error_response("Nama perangkat harus berupa teks", 400)
    if (not password and not pin) or (password and pin):
        return error_response("Isi salah satu: password atau PIN", 400)
    if pin and (len(pin) != 6 or not pin.isdigit()):
        return error_response("PIN harus terdiri dari 6 digit", 400)
    if password and not isinstance(password, str):
        return error_response("Password harus berupa teks", 400)

    user = User.query_active().filter_by(username=username, is_active=True).first()
    valid_password = (
        user is not None
        and bool(password)
        and verify_password(user.password_hash, password)
    )
    valid_pin = (
        user is not None
        and bool(pin)
        and user.pin_hash is not None
        and verify_password(user.pin_hash, pin)
    )
    if not user or not (valid_password or valid_pin):
        return error_response("Username atau password salah", 401)

    # Check device if device_id provided
    if device_id:
        existing_device = Device.query.filter_by(user_id=user.id, device_id=device_id).first()
        if existing_device:
            if existing_device.is_revoked:
                return error_response("Perangkat ini telah dicabut hak aksesnya oleh Admin", 403)
            existing_device.last_login_at = datetime.now(timezone.utc)
            existing_device.device_name = device_name
        else:
            # Check maximum active devices limit
            max_devices = current_app.config.get("MAX_ACTIVE_DEVICES_PER_USER", 3)
            active_devices_count = Device.query.filter_by(user_id=user.id, is_revoked=False).count()
            if active_devices_count >= max_devices:
                return error_response(
                    f"Batas perangkat aktif ({max_devices}) tercapai. Cabut perangkat lama terlebih dahulu.",
                    403
                )
            new_device = Device(
                user_id=user.id,
                device_id=device_id,
                device_name=device_name
            )
            db.session.add(new_device)

        db.session.commit()

    # Create JWT tokens with claims
    additional_claims = {
        "role": user.role,
        "name": user.name,
        "device_id": device_id
    }
    access_token = create_access_token(identity=user.id, additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=user.id, additional_claims=additional_claims)

    return api_response({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "role": user.role,
        }
    }, "Login berhasil")


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Generate a new access token from refresh token."""
    user_id = get_jwt_identity()
    claims = get_jwt()
    user = db.session.get(User, user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        return error_response("User tidak aktif atau tidak ditemukan", 401)

    additional_claims = {
        "role": user.role,
        "name": user.name,
        "device_id": claims.get("device_id")
    }
    new_access_token = create_access_token(identity=user.id, additional_claims=additional_claims)
    return api_response({"access_token": new_access_token}, "Token refreshed")


@auth_bp.route("/verify-pin", methods=["POST"])
@limiter.limit(lambda: current_app.config["AUTH_PIN_RATE_LIMIT"])
@jwt_required()
def verify_pin():
    """Verify 6-digit PIN for quick authorization (void, discount, kasir auth)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("Format permintaan tidak valid", 400)
    pin = str(data.get("pin", "")).strip()
    target_role = data.get("role")  # e.g. verify if it's admin PIN

    if not pin or len(pin) != 6 or not pin.isdigit():
        return error_response("PIN harus 6 digit", 400)

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user or user.deleted_at is not None:
        return error_response("User tidak ditemukan", 404)

    # If verification requires admin role PIN specifically
    if target_role == "admin":
        # Find any active admin/super_admin with this PIN
        admins = User.query.filter(User.role.in_(["admin", "super_admin"]), User.is_active.is_(True)).all()
        for adm in admins:
            if adm.pin_hash and verify_password(adm.pin_hash, pin):
                serializer = URLSafeTimedSerializer(
                    current_app.config["SECRET_KEY"],
                    salt="jou-coffee-admin-approval"
                )
                approval_token = serializer.dumps({
                    "purpose": "order_discount",
                    "user_id": user_id,
                    "approved_by": adm.id
                })
                return api_response({
                    "verified": True,
                    "verified_by": adm.name,
                    "approval_token": approval_token,
                    "expires_in": 300
                }, "PIN Admin valid")
        return error_response("PIN Admin salah", 401)

    # Standard check for current user PIN
    if user.pin_hash and verify_password(user.pin_hash, pin):
        return api_response({"verified": True}, "PIN valid")
    return error_response("PIN salah", 401)


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """Logout endpoint."""
    return api_response(None, "Logout berhasil")

