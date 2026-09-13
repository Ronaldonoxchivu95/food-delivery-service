from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./order.db"

    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    ADMIN_REGISTRATION_SECRET: str = "admin-secret"

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    EVENTS_EXCHANGE: str = "orders_events"

    RESTAURANT_SERVICE_URL: str = "http://localhost:8001"
    RESTAURANT_SERVICE_TIMEOUT_SECONDS: float = 5.0

    SERVICE_NAME: str = "order-service"


settings = Settings()
