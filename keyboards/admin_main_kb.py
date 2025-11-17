from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загрузить таблицу проблем", callback_data="admin:upload_problems")],
        [InlineKeyboardButton(text="📥 Загрузить сотрудников", callback_data="admin:upload_staff")],  # 👈 НОВАЯ КНОПКА
        [InlineKeyboardButton(text="📊 Статистика проблем", callback_data="admin:stats_problems")],
        [InlineKeyboardButton(text="👥 Управление администраторами", callback_data="admin:admins")],
        [InlineKeyboardButton(text="👥 Пользователи бота", callback_data="admin:users")],
        [InlineKeyboardButton(text="🧾 Тест Акта", callback_data="admin:akt")],
        [InlineKeyboardButton(text="🗑 Удалить список проблем", callback_data="admin:delete_plists")],
    ])