# reminders.py
import asyncio
from datetime import date, datetime
from typing import Iterable

from aiogram import Bot

from db import session_scope
from crud import get_problems_for_reminder
from models import Problem


async def send_due_reminders(bot: Bot):
    today = date.today()
    async with session_scope() as s:
        items = await get_problems_for_reminder(s, today)  # как раньше: список Problem

    for prob in items:
        due = datetime.strptime(prob.due_date.strip(), "%Y-%m-%d").date()
        days_left = (due - today).days
        if not (0 <= days_left <= 3):
            continue

        plist = prob.plist
        text_base = (
            f"⏰ Напоминание по задаче #{prob.number} из списка «{plist.title or plist.code}».\n\n"
            f"Описание: {prob.title}\n"
            f"Срок исполнения: {due.strftime('%Y-%m-%d')}."
        )

        for tg_id in prob.assignees:    # 👈 несколько людей
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text=text_base,
                )
            except Exception:
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
