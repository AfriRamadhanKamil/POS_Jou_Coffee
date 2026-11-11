import os
from flask import Flask, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.config import config_by_name
from app.extensions import db, migrate, jwt, ma, cors, socketio


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    flask_app = Flask(__name__)
    flask_app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))
    if config_name == "production":
        required_environment = (
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY",
            "JWT_SECRET_KEY",
            "QR_HMAC_SECRET",
            "PAYMENT_GATEWAY_SERVER_KEY",
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

    # Initialize extensions
    db.init_app(flask_app)
    migrate.init_app(flask_app, db)
    jwt.init_app(flask_app)
    ma.init_app(flask_app)
    cors.init_app(flask_app)
    
    # Local development and tests can run without Redis. Production uses Redis
    # so Socket.IO events are shared between backend worker processes.
    message_queue = (
        flask_app.config.get("REDIS_URL")
        if config_name == "production"
        else flask_app.config.get("SOCKETIO_MESSAGE_QUEUE")
    )
    socketio.init_app(flask_app, message_queue=message_queue)

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
                "data": {"api": "connected", "database": "unavailable"},
                "version": "1.0.0"
            }), 503

        return jsonify({
            "success": True,
            "message": "POS Jou Coffee API and database are healthy",
            "data": {"api": "connected", "database": "connected"},
            "version": "1.0.0"
        })

    # Import socketio events & models
    with flask_app.app_context():
        from app.realtime import events
        import app.models  # ensure all models registered for migrations

    return flask_app
