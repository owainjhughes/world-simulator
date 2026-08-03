import asyncio

import aio_pika

AMQP_URL = "amqp://dev:dev@localhost/"


async def main() -> None:
    connection = await aio_pika.connect_robust(AMQP_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            "world.events", aio_pika.ExchangeType.TOPIC, durable=True
        )

        for i in range(10):
            body = f"CreatureBorn #{i}".encode()
            await exchange.publish(
                aio_pika.Message(body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key="ecology.wylenn.creature.born",
            )
            print(f"published {body.decode()}")
            await asyncio.sleep(0.5)


asyncio.run(main())
