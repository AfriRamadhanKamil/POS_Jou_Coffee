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


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
