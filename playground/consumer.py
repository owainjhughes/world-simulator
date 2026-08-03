import asyncio

import aio_pika

AMQP_URL = "amqp://dev:dev@localhost/"


async def main() -> None:
    connection = await aio_pika.connect_robust(AMQP_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    exchange = await channel.declare_exchange(
        "world.events", aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue("hello.ecology", durable=True)
    await queue.bind(exchange, routing_key="ecology.#")

    print("waiting for messages (ctrl-c to stop)")
    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                print(f"received {message.body.decode()}")
                await asyncio.sleep(2)


asyncio.run(main())
