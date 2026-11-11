from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _hasher = PasswordHasher()
    def hash_password(password: str) -> str:
        return _hasher.hash(password)
    def verify_password(hashed: str, password: str) -> bool:
        try:
            return _hasher.verify(hashed, password)
        except VerifyMismatchError:
            return False
        except Exception:
            # Fallback to werkzeug in case it was hashed with werkzeug
            return check_password_hash(hashed, password)
except ImportError:
    def hash_password(password: str) -> str:
        return generate_password_hash(password)
    def verify_password(hashed: str, password: str) -> bool:
        return check_password_hash(hashed, password)


# Roles definition
ROLE_KASIR = "kasir"
ROLE_ADMIN = "admin"
ROLE_SUPER_ADMIN = "super_admin"
ALL_ROLES = [ROLE_KASIR, ROLE_ADMIN, ROLE_SUPER_ADMIN]


def role_required(*allowed_roles):
    """Decorator to enforce role-based access control (RBAC)."""
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            user_role = claims.get("role")
            if user_role not in allowed_roles:
                return jsonify({
                    "success": False,
                    "message": f"Forbidden: requires role '{', '.join(allowed_roles)}'",
                    "data": None
                }), 403
            return fn(*args, **kwargs)
        return decorator
    return wrapper

