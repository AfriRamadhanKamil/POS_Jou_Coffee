import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "jou-coffee-dev-secret-change-in-production")
    
    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///jou_coffee.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    } if "sqlite" not in os.getenv("DATABASE_URL", "sqlite") else {}

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


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-jwt-secret-key"


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
