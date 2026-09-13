"""RabbitMQ publisher: order-service announces order lifecycle events on a
durable topic exchange. restaurant-service (and, in the future, a
notifications-service) subscribe independently — order-service does not
know or care who's listening.

Publishing is best-effort: if RabbitMQ is temporarily unreachable, we log a
warning and let the HTTP request succeed anyway (the order is already
committed to Postgres). Losing an analytics-style event is preferable to
failing a customer's order.
"""

import json
import logging

import aio_pika

from app.config import settings

logger = logging.getLogger("order_service.messaging")


class OrderEventsPublisher:
    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        try:
            self._connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(
                settings.EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
            )
            logger.info("Connected to RabbitMQ exchange=%s", settings.EVENTS_EXCHANGE)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not connect to RabbitMQ at startup: %s", exc)
            self._connection = None
            self._exchange = None

    async def publish(self, routing_key: str, payload: dict) -> None:
        try:
            if self._exchange is None:
                await self.connect()
            if self._exchange is None:
                logger.warning("RabbitMQ unavailable, dropping event %s", routing_key)
                return
            message = aio_pika.Message(
                body=json.dumps(payload, default=str).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )
            await self._exchange.publish(message, routing_key=routing_key)
        except Exception as exc:  # noqa: BLE001 - never let a broker hiccup break the API
            logger.warning("Failed to publish event %s: %s", routing_key, exc)

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()


publisher = OrderEventsPublisher()
