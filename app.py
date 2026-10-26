"""Точка входа бота: запуск поллинга, фонового watcher'а и graceful shutdown."""
import asyncio
import contextlib
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import settings
from db import dispose_db, init_db
from handlers import admin, profile, schedule, start
from services import reminders, watcher

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан — заполни .env")
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан — заполни .env")

    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode="HTML")
    )
    
    dp = Dispatcher()
    dp.include_routers(start.router, profile.router, schedule.router, admin.router)

    watcher_task = asyncio.create_task(watcher.watcher_loop(bot))
    reminders_task = asyncio.create_task(reminders.reminders_loop(bot))

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def request_shutdown() -> None:
        logger.info("Получен сигнал завершения")
        stop.set()

    if hasattr(loop, "add_signal_handler"):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, request_shutdown)

    polling_task = asyncio.create_task(dp.start_polling(bot))
    stop_task = asyncio.create_task(stop.wait())

    try:
        done, _ = await asyncio.wait(
            {polling_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            if task is polling_task:
                exc = polling_task.exception()
                if exc is not None:
                    logger.error("polling завершился с ошибкой: %s", exc)
    finally:
        logger.info("Останавливаю бота…")
        for task in (polling_task, watcher_task, reminders_task, stop_task):
            task.cancel()
        for task in (polling_task, watcher_task, reminders_task, stop_task):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await bot.session.close()
        await dispose_db()
    logger.info("Остановлен")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())