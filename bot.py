import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from db import init_db
from handlers import user_router, admin_router, common_router
from logging_config import setup_logging
from middlewares.role_mw import RoleMiddleware
from reminders import send_due_reminders
import logging
logging.basicConfig(level=logging.INFO)

def ensure_token():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is not set. Put it to .env")

async def main():
    setup_logging()

    ensure_token()
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # каждый день в
    scheduler.add_job(
        send_due_reminders,
        trigger="cron",
        hour=22,
        minute=30,
        args=[bot],
    )

    scheduler.start()

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())
    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    await dp.start_polling(bot)

    # # 🔔 Запускаем фоновый шедулер напоминаний
    # asyncio.create_task(daily_reminder_worker(bot))

if __name__ == "__main__":
    asyncio.run(main())
