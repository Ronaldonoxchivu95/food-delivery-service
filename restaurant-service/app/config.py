from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./restaurant.db"
    JWT_SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    EVENTS_EXCHANGE: str = "orders_events"
    ORDER_EVENTS_QUEUE: str = "restaurant_service.order_events"

    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 60

    SERVICE_NAME: str = "restaurant-service"


settings = Settings()
