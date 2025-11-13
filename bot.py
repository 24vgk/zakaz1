import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from db import init_db
from handlers import user_router, admin_router, common_router
from middlewares.role_mw import RoleMiddleware
from reminders import daily_reminder_worker
import logging
logging.basicConfig(level=logging.INFO)

def ensure_token():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is not set. Put it to .env")

async def main():
    ensure_token(); await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())
    dp.include_router(common_router)
    dp.include_router(admin_router)
    dp.include_router(user_router)
    await dp.start_polling(bot)

    # 🔔 Запускаем фоновый шедулер напоминаний
    asyncio.create_task(daily_reminder_worker(bot))

if __name__ == "__main__":
    asyncio.run(main())
