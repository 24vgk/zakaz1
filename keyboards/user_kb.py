
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список проблем", callback_data="user:problems")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="user:stats")],
    ])
