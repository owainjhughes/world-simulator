import aio_pika

from domain.events import Event

EXCHANGE = "world.events"


class EventPublisher:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection = None
        self._exchange = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        channel = await self._connection.channel()
        self._exchange = await channel.declare_exchange(
            EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )

    async def publish(self, event: Event) -> None:
        message = aio_pika.Message(
            event.model_dump_json().encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=event.routing_key)

    async def close(self) -> None:
        await self._connection.close()
