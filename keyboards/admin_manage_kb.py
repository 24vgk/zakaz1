from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admins_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin:add_admin"),
            InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin:del_admin"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back_main")],
    ])

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="admin:cancel")],
    ])