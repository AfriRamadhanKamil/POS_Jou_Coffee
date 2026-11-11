import os
from flask import Flask, jsonify
from app.config import config_by_name
from app.extensions import db, migrate, jwt, ma, cors, socketio


def create_app(config_name=None):
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    flask_app = Flask(__name__)
    flask_app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    # Initialize extensions
    db.init_app(flask_app)
    migrate.init_app(flask_app, db)
    jwt.init_app(flask_app)
    ma.init_app(flask_app)
    cors.init_app(flask_app)
    
    # Initialize socketio with redis message queue if not in testing/sqlite
    redis_url = flask_app.config.get("REDIS_URL")
    if flask_app.config.get("TESTING"):
        socketio.init_app(flask_app)
    else:
        try:
            socketio.init_app(flask_app, message_queue=redis_url)
        except Exception:
            # Fallback to local memory queue if redis is unavailable in dev
            socketio.init_app(flask_app)

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
        return jsonify({
            "success": True,
            "message": "POS Jou Coffee API is healthy",
            "version": "1.0.0"
        })

    # Import socketio events & models
    with flask_app.app_context():
        from app.realtime import events
        import app.models  # ensure all models registered for migrations

    return flask_app
