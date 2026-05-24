import asyncio
import logging

from worker.consumer import ServiceBusConsumer

logger = logging.getLogger(__name__)


async def main() -> None:
    consumer = ServiceBusConsumer()
    logger.info("Starting provisioning worker")
    await consumer.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
