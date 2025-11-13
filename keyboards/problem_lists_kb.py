# keyboards/problem_lists_kb.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def problem_lists_menu(codes: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=code, callback_data=f"user:plist:{code}") ] for code in codes]
    return InlineKeyboardMarkup(inline_keyboard=rows)



def problem_detail_menu(list_code: str, number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📤 Загрузить отчёт",
            callback_data=f"user:upload_for:{list_code}:{number}"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад к списку проблем",
            callback_data=f"user:back_problems:{list_code}"
        )],
    ])