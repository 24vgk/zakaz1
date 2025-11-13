# handlers/common.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from keyboards.admin_main_kb import admin_main_menu
from texts import START
from keyboards.user_kb import main_menu

common_router = Router(name="common")

@common_router.message(F.text == "/start")
async def start_all(msg: Message, event_from_user_role: str | None = None):
    if event_from_user_role == "user":
        await msg.answer(START, reply_markup=main_menu())
    elif event_from_user_role == "admin":
        await msg.answer(
            "👋 Привет, администратор!\nВыберите действие:",
            reply_markup=admin_main_menu()
        )
    else:
        await msg.answer(START, reply_markup=main_menu())
        # await msg.answer("Привет! Ваша роль не определена. Обратитесь к администратору.")

# @common_router.message()
# async def debug_chat_id(message: Message):
#     await message.answer(f"Chat ID: <code>{message.chat.id}</code>")