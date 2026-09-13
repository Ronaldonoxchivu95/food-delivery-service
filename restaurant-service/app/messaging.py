"""RabbitMQ consumer: restaurant-service reacts to order lifecycle events
published by order-service, without either service calling the other
synchronously.

Event types consumed (topic exchange "orders_events"):
  - order.created         -> bump RestaurantStats.total_orders
  - order.status_changed  -> logged (hook point for future features)
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import select

from app.cache import cache_delete_by_prefix
from app.config import settings
from app.database import AsyncSessionLocal
from app.metrics import ORDER_EVENTS_CONSUMED
from app.models import RestaurantStats

logger = logging.getLogger("restaurant_service.messaging")


async def _handle_order_created(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    if restaurant_id is None:
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RestaurantStats).where(RestaurantStats.restaurant_id == restaurant_id)
        )
        stats = result.scalar_one_or_none()
        if stats is None:
            stats = RestaurantStats(restaurant_id=restaurant_id, total_orders=0)
            session.add(stats)
        stats.total_orders += 1
        stats.last_order_at = datetime.now(timezone.utc)
        await session.commit()
    # The restaurant's public listing may surface popularity/stats, so drop
    # any cached copies.
    await cache_delete_by_prefix(f"restaurant:{restaurant_id}")


async def _handle_status_changed(payload: dict) -> None:
    logger.info("Order status changed: %s", payload)


_HANDLERS = {
    "order.created": _handle_order_created,
    "order.status_changed": _handle_status_changed,
}


async def _on_message(message: AbstractIncomingMessage) -> None:
    async with message.process(ignore_processed=True):
        routing_key = message.routing_key or ""
        try:
            payload = json.loads(message.body.decode())
        except json.JSONDecodeError:
            logger.warning("Dropping malformed message on routing key %s", routing_key)
            return

        handler = _HANDLERS.get(routing_key)
        ORDER_EVENTS_CONSUMED.labels(event_type=routing_key or "unknown").inc()
        if handler is None:
            logger.debug("No handler for routing key %s, ignoring", routing_key)
            return
        try:
            await handler(payload)
        except Exception:  # noqa: BLE001 - never let one bad message kill the consumer
            logger.exception("Error handling event %s: %s", routing_key, payload)


class OrderEventsConsumer:
    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run_with_retry())

    async def _run_with_retry(self) -> None:
        delay = 2
        while not self._stopping:
            try:
                await self._consume_forever()
            except Exception as exc:  # noqa: BLE001
                if self._stopping:
                    return
                logger.warning("RabbitMQ consumer error (%s); retrying in %ss", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def _consume_forever(self) -> None:
        self._connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with self._connection:
            channel = await self._connection.channel()
            await channel.set_qos(prefetch_count=10)
            exchange = await channel.declare_exchange(
                settings.EVENTS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
            )
            queue = await channel.declare_queue(settings.ORDER_EVENTS_QUEUE, durable=True)
            await queue.bind(exchange, routing_key="order.*")
            logger.info("Listening for order events on queue=%s", settings.ORDER_EVENTS_QUEUE)
            await queue.consume(_on_message)
            await asyncio.Future()  # run until cancelled

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()


consumer = OrderEventsConsumer()
