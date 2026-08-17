import json
from collections.abc import Awaitable, Callable

import aio_pika

EXCHANGE = "world.events"
DEAD_LETTER_EXCHANGE = "world.events.dead"

Handler = Callable[[str, dict], Awaitable[None]]


class EventConsumer:
    def __init__(
        self,
        url: str,
        queue_name: str,
        routing_keys: list[str],
        exclusive: bool = False,
    ) -> None:
        self._url = url
        self._queue_name = queue_name
        self._routing_keys = routing_keys
        self._exclusive = exclusive
        self._connection = None
        self._exchange = None
        self._queue = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self._url)
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=10)

        self._exchange = await channel.declare_exchange(
            EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )

        if self._exclusive:
            self._queue = await channel.declare_queue(exclusive=True)
        else:
            dead_letters = await channel.declare_exchange(
                DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
            )
            dead_queue = await channel.declare_queue(
                f"{self._queue_name}.dead", durable=True
            )
            await dead_queue.bind(dead_letters, routing_key="#")

            self._queue = await channel.declare_queue(
                self._queue_name,
                durable=True,
                arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE},
            )

        for routing_key in self._routing_keys:
            await self.bind(routing_key)

    async def bind(self, routing_key: str) -> None:
        await self._queue.bind(self._exchange, routing_key=routing_key)

    async def unbind(self, routing_key: str) -> None:
        await self._queue.unbind(self._exchange, routing_key=routing_key)

    async def consume(self, handler: Handler) -> None:
        async with self._queue.iterator() as messages:
            async for message in messages:
                async with message.process(requeue=False):
                    await handler(message.routing_key, json.loads(message.body))

    async def close(self) -> None:
        await self._connection.close()
