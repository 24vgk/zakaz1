# reminders.py
import asyncio
from datetime import date
from typing import Iterable

from aiogram import Bot

from db import session_scope
from crud import get_problems_for_reminder
from models import Problem


async def send_due_reminders(bot: Bot):
    """
    Разовая проверка: на сегодня ищем задачи,
    по которым нужно напомнить, и шлём сообщения исполнителям.
    """
    today = date.today()

    async with session_scope() as s:
        items = await get_problems_for_reminder(s, today)

    if not items:
        return

    for prob, due_date, days_left in items:
        # assignee — это Telegram ID
        chat_id = prob.assignee
        if not chat_id:
            continue

        # собираем человеческий текст
        if days_left > 0:
            days_text = {
                3: "через 3 дня",
                2: "через 2 дня",
                1: "завтра",
            }.get(days_left, f"через {days_left} дней")
        else:
            days_text = "сегодня"

        plist = prob.plist  # связь уже подгружена в get_problems_for_reminder

        text = (
            f"⏰ Напоминание по задаче #{prob.number} из списка «{plist.title or plist.code}».\n\n"
            f"Описание: {prob.title}\n"
            f"Срок исполнения: {due_date.strftime('%Y-%m-%d')} ({days_text})."
        )

        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            # на всякий случай не роняем шедулер
            continue


async def daily_reminder_worker(bot: Bot):
    """
    Бесконечная задача, которая раз в сутки вызывает send_due_reminders.

    Для простоты: запускается при старте бота, затем спит 24 часа.
    При рестарте бота напоминание сработает ещё раз в день рестарта.
    """
    while True:
        try:
            await send_due_reminders(bot)
        except Exception as e:
            print(f"[REMINDER] Ошибка при отправке напоминаний: {e}")
        # спим сутки
        await asyncio.sleep(24 * 60 * 60)
