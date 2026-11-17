import os
from uuid import uuid4
from flask import Flask, jsonify, request
import redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix
from app.config import config_by_name
from app.extensions import db, migrate, jwt, ma, cors, limiter, socketio
from app.common.response import error_response


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    flask_app = Flask(__name__)
    flask_app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))
    if config_name == "testing":
        flask_app.config["RATELIMIT_KEY_PREFIX"] = f"test-{uuid4().hex}"
    if flask_app.config.get("SENTRY_DSN"):
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        sentry_sdk.init(
            dsn=flask_app.config["SENTRY_DSN"],
            environment=flask_app.config["SENTRY_ENVIRONMENT"],
            integrations=[FlaskIntegration()],
            send_default_pii=False
        )
    configured_origins = flask_app.config.get("CORS_ORIGINS", "*")
    cors_origins = (
        [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
        if isinstance(configured_origins, str)
        else configured_origins
    )
    if config_name == "production":
        required_environment = (
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY",
            "JWT_SECRET_KEY",
            "QR_HMAC_SECRET",
            "PAYMENT_GATEWAY_SERVER_KEY",
            "CORS_ORIGINS",
        )
        missing = [name for name in required_environment if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                "Konfigurasi production wajib diisi: " + ", ".join(missing)
            )
        for name in ("SECRET_KEY", "JWT_SECRET_KEY", "QR_HMAC_SECRET"):
            if len(os.environ[name]) < 32:
                raise RuntimeError(f"{name} harus memiliki minimal 32 karakter di production")
        if not flask_app.config["SQLALCHEMY_DATABASE_URI"].startswith(
            ("mysql://", "mysql+pymysql://")
        ):
            raise RuntimeError("Production wajib menggunakan MySQL melalui DATABASE_URL")
        if not flask_app.config["RATELIMIT_STORAGE_URI"].startswith(
            ("redis://", "rediss://")
        ):
            raise RuntimeError("Rate limiting production wajib menggunakan Redis")
        if not cors_origins or "*" in cors_origins:
            raise RuntimeError("CORS_ORIGINS production wajib berisi origin HTTPS yang spesifik")
        if any(not origin.startswith("https://") for origin in cors_origins):
            raise RuntimeError("Semua CORS_ORIGINS production wajib menggunakan HTTPS")

    # Initialize extensions
    db.init_app(flask_app)
    migrate.init_app(flask_app, db)
    jwt.init_app(flask_app)
    ma.init_app(flask_app)
    cors.init_app(flask_app, resources={r"/api/*": {"origins": cors_origins}})
    limiter.init_app(flask_app)

    @flask_app.errorhandler(429)
    def rate_limit_exceeded(error):
        return error_response("Terlalu banyak permintaan. Silakan coba lagi nanti.", 429)
    
    # Local development and tests can run without Redis. Production uses Redis
    # so Socket.IO events are shared between backend worker processes.
    message_queue = (
        flask_app.config.get("REDIS_URL")
        if config_name == "production"
        else flask_app.config.get("SOCKETIO_MESSAGE_QUEUE")
    )
    socketio.init_app(
        flask_app,
        message_queue=message_queue,
        cors_allowed_origins=cors_origins
    )
    if config_name == "production":
        flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1)

    @flask_app.before_request
    def require_production_https():
        if config_name == "production" and not request.is_secure:
            return error_response("HTTPS wajib digunakan", 426)

    @flask_app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if config_name == "production" and request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains"
            )
        return response

    # JWT Error handlers
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        return jsonify({
            "success": False,
            "message": "Missing authorization token",
            "data": None
        }), 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "success": False,
            "message": "Token has expired",
            "data": None
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        return jsonify({
            "success": False,
            "message": "Signature verification failed",
            "data": None
        }), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({
            "success": False,
            "message": "Token revoked or account/device inactive",
            "data": None
        }), 401

    @jwt.token_in_blocklist_loader
    def token_is_revoked(jwt_header, jwt_payload):
        from app.auth.models import Device, User

        user_id = jwt_payload.get("sub")
        device_id = jwt_payload.get("device_id")
        user = db.session.get(User, user_id) if user_id else None
        if (
            not user
            or not user.is_active
            or user.deleted_at is not None
            or jwt_payload.get("role") != user.role
            or not device_id
        ):
            return True

        device = Device.query.filter_by(user_id=user.id, device_id=device_id).first()
        return (
            not device
            or device.is_revoked
            or device.deleted_at is not None
        )

    # Generic error handlers
    @flask_app.errorhandler(404)
    def not_found_error(error):
        return jsonify({
            "success": False,
            "message": "Endpoint tidak ditemukan",
            "data": None
        }), 404

    @flask_app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({
            "success": False,
            "message": "Terjadi kesalahan internal server",
            "data": None
        }), 500

    # Register Blueprints
    from app.auth.routes import auth_bp
    from app.users.routes import users_bp
    from app.catalog.routes import catalog_bp
    from app.inventory.routes import inventory_bp
    from app.orders.routes import orders_bp
    from app.public.routes import public_bp
    from app.finance.routes import finance_bp
    from app.reports.routes import reports_bp
    from app.tables.routes import tables_bp
    from app.sync.routes import sync_bp

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(users_bp)
    flask_app.register_blueprint(catalog_bp)
    flask_app.register_blueprint(inventory_bp)
    flask_app.register_blueprint(orders_bp)
    flask_app.register_blueprint(public_bp)
    flask_app.register_blueprint(finance_bp)
    flask_app.register_blueprint(reports_bp)
    flask_app.register_blueprint(tables_bp)
    flask_app.register_blueprint(sync_bp)

    # Health check route
    @flask_app.route("/api/v1/health", methods=["GET"])
    def health_check():
        try:
            db.session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            db.session.rollback()
            flask_app.logger.exception("Database readiness check failed")
            return jsonify({
                "success": False,
                "message": "Backend aktif tetapi database tidak dapat diakses",
                "data": {
                    "api": "connected",
                    "database": "unavailable",
                    "redis": "not_checked"
                },
                "version": "1.0.0"
            }), 503

        redis_url = (
            flask_app.config.get("REDIS_URL")
            if config_name == "production"
            else flask_app.config.get("SOCKETIO_MESSAGE_QUEUE")
        )
        redis_status = "not_required"
        if redis_url:
            try:
                redis_client = redis.Redis.from_url(redis_url)
                try:
                    redis_client.ping()
                finally:
                    redis_client.close()
            except redis.exceptions.RedisError:
                flask_app.logger.exception("Redis readiness check failed")
                return jsonify({
                    "success": False,
                    "message": "Backend aktif tetapi Redis tidak dapat diakses",
                    "data": {
                        "api": "connected",
                        "database": "connected",
                        "redis": "unavailable"
                    },
                    "version": "1.0.0"
                }), 503
            redis_status = "connected"

        return jsonify({
            "success": True,
            "message": "POS Jou Coffee API dependencies are healthy",
            "data": {
                "api": "connected",
                "database": "connected",
                "redis": redis_status
            },
            "version": "1.0.0"
        })

    # Import socketio events & models
    with flask_app.app_context():
        from app.realtime import events
        import app.models  # ensure all models registered for migrations
        from app.sync.events import register_sync_events
        register_sync_events()

    return flask_app
