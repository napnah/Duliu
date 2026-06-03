import asyncio
import logging

from duliu.config import settings
from duliu.db.session import async_session, init_db
from duliu.worker.handlers import poll_and_run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("duliu.worker")


async def loop() -> None:
    await init_db()
    logger.info("Duliu worker started, polling every %ss", settings.job_poll_seconds)
    while True:
        async with async_session() as session:
            n = await poll_and_run(session)
            if n:
                logger.info("Processed %s job(s)", n)
        await asyncio.sleep(settings.job_poll_seconds)


def run() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    run()
