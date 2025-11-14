from datetime import date, datetime

from aiogram import Bot

from db import session_scope
from crud import get_problems_for_reminder


async def send_due_reminders(bot: Bot):
    today = date.today()

    # забираем уже подготовленные словари
    async with session_scope() as s:
        items = await get_problems_for_reminder(s, today)

    # здесь НЕТ ORM-объектов, только обычные dict — ничего не "отвалится" от сессии
    for item in items:
        number      = item["number"]
        title       = item["title"]
        due         = item["due_date"]      # уже date
        days_left   = item["days_left"]
        assignees   = item["assignees"]     # list[int]
        plist_title = item["plist_title"]
        plist_code  = item["plist_code"]

        # на всякий случай ещё раз фильтр, но можно и убрать:
        if not (0 <= days_left <= 3):
            continue

        text_base = (
            f"⏰ Напоминание по задаче #{number} из списка "
            f"«{plist_title or plist_code}».\n\n"
            f"Описание: {title}\n"
            f"Срок исполнения: {due.strftime('%Y-%m-%d')}."
        )

        for tg_id in assignees:
            try:
                await bot.send_message(chat_id=tg_id, text=text_base)
            except Exception:
                # пользователь мог заблокировать бота и т.п. — просто пропускаем
                continue
