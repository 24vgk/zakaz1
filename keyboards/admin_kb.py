
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
def review_kb(report_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:accept:{report_id}:{user_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject:{report_id}:{user_id}"),
    ]])
