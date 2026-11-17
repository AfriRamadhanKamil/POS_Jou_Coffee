import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DATABASE_URL = (
    "mysql+pymysql://root:@127.0.0.1:3306/jou_coffee?charset=utf8mb4"
)


class Config:
    """Base configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "jou-coffee-dev-secret-change-in-production")
    
    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = (
        {}
        if SQLALCHEMY_DATABASE_URI.startswith("sqlite:")
        else {"pool_pre_ping": True, "pool_recycle": 3600}
    )

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    QR_ORDER_RATE_LIMIT = os.getenv("QR_ORDER_RATE_LIMIT", "10 per minute")
    QR_ORDER_TABLE_RATE_LIMIT = os.getenv("QR_ORDER_TABLE_RATE_LIMIT", "60 per minute")
    AUTH_LOGIN_RATE_LIMIT = os.getenv("AUTH_LOGIN_RATE_LIMIT", "10 per minute")
    AUTH_PIN_RATE_LIMIT = os.getenv("AUTH_PIN_RATE_LIMIT", "5 per minute")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", os.getenv("FLASK_ENV", "development"))
    FCM_SERVICE_ACCOUNT_FILE = os.getenv("FCM_SERVICE_ACCOUNT_FILE", "")

    # JWT
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jou-jwt-dev-secret-key-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "7"))
    )

    # QR & Security
    QR_HMAC_SECRET = os.getenv("QR_HMAC_SECRET", "table-qr-signed-secret-change-in-prod")
    MAX_ACTIVE_DEVICES_PER_USER = int(os.getenv("MAX_ACTIVE_DEVICES_PER_USER", "3"))
    OFFLINE_SESSION_MAX_DAYS = int(os.getenv("OFFLINE_SESSION_MAX_DAYS", "7"))
    MAX_ORDER_DISCOUNT_PERCENT = float(os.getenv("MAX_ORDER_DISCOUNT_PERCENT", "10"))

    # Payment Gateway
    PAYMENT_GATEWAY_PROVIDER = os.getenv("PAYMENT_GATEWAY_PROVIDER", "midtrans")
    PAYMENT_GATEWAY_SERVER_KEY = os.getenv("PAYMENT_GATEWAY_SERVER_KEY", "")
    PAYMENT_GATEWAY_CLIENT_KEY = os.getenv("PAYMENT_GATEWAY_CLIENT_KEY", "")
    PAYMENT_GATEWAY_BASE_URL = os.getenv("PAYMENT_GATEWAY_BASE_URL", "https://api.sandbox.midtrans.com")


class DevelopmentConfig(Config):
    DEBUG = True
    # Local development runs Socket.IO in-process; Redis is only required when
    # explicitly configured for a multi-process setup.
    SOCKETIO_MESSAGE_QUEUE = os.getenv("SOCKETIO_MESSAGE_QUEUE")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SOCKETIO_MESSAGE_QUEUE = None
    JWT_SECRET_KEY = "test-jwt-secret-key-for-jou-coffee-32"
    PAYMENT_GATEWAY_SERVER_KEY = ""
    PAYMENT_GATEWAY_CLIENT_KEY = ""


class ProductionConfig(Config):
    DEBUG = False
    RATELIMIT_STORAGE_URI = os.getenv(
        "RATELIMIT_STORAGE_URI",
        os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    )


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
