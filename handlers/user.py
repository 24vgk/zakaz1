# handlers/user.py
from __future__ import annotations

from io import BytesIO
import html

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from sqlalchemy import select

from config import GROUP_CHAT_ID
from keyboards.user_kb import main_menu
from keyboards.admin_kb import review_kb
from texts import (
    START, ASK_DATA, REPORT_SENT, USER_STATS,
)
from db import session_scope
from crud import (
    get_or_create_user,
    create_report,
    add_media,
    user_stats,
    MediaType,
    set_problem_status,
)
from models import (
    Problem,
    ProblemList,
    ProblemStatus,
    User as MUser,
    Role,
)
from utils.files import ensure_dirs, build_paths, save_bytes_to_all


# ===== Гард роли =====
async def guard_user(event, event_from_user_role: str | None) -> bool:
    if event_from_user_role != "user":
        text = "Эта функция доступна только пользователям."
        # CallbackQuery vs Message
        if hasattr(event, "answer") and event.__class__.__name__ == "CallbackQuery":
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        return False
    return True

async def _get_group_topic_for_list(list_code: str) -> int | None:
    """
    Возвращает message_thread_id темы в группе для списка list_code.
    Ничего не создаёт, просто читает ProblemList.group_topic_id.
    """
    if not GROUP_CHAT_ID:
        return None

    async with session_scope() as s:
        row = await s.execute(
            select(ProblemList.group_topic_id).where(ProblemList.code == list_code)
        )
        topic_id = row.scalar_one_or_none()

    if not topic_id:
        return None

    return int(topic_id)


user_router = Router(name="user")


# ===== Состояния =====
class ReportStates(StatesGroup):
    waiting_payload = State()  # ждём файлы по уже выбранной проблеме


# ===== Лейблы статусов =====
STATUS_LABELS = {
    ProblemStatus.IN_PROGRESS: "В работе",
    ProblemStatus.REPORT_SENT: "Отчёт отправлен",
    ProblemStatus.ACCEPTED: "Отчёт принят",
    ProblemStatus.REJECTED: "Отчёт отклонён",
}


# ===== Локальные клавиатуры =====

def lists_menu(codes: list[str]) -> InlineKeyboardMarkup:
    """Список списков проблем."""
    kb = [
        [InlineKeyboardButton(text=code, callback_data=f"user:plist_view:{code}")]
        for code in codes
    ]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="user:back_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def problems_menu(list_code: str, problems: list[dict]) -> InlineKeyboardMarkup:
    """Список проблем в выбранном списке."""
    rows: list[list[InlineKeyboardButton]] = []
    for p in problems:
        num = p["number"]
        title = p["title"] or ""
        short = title if len(title) <= 40 else title[:37] + "..."
        rows.append([
            InlineKeyboardButton(
                text=f"#{num} — {short}",
                callback_data=f"user:prob:{list_code}:{num}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад к спискам",
            callback_data="user:back_lists",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def problem_detail_menu(list_code: str, number: int) -> InlineKeyboardMarkup:
    """Карточка проблемы: загрузить отчёт / назад."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📤 Загрузить отчёт",
                callback_data=f"user:upload_for:{list_code}:{number}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад к списку проблем",
                callback_data=f"user:back_problems:{list_code}",
            )
        ],
    ])


# ===== Вспомогательные функции =====

async def _load_user_lists(user_tg_id: int) -> list[str]:
    """
    Открытые списки, в которых у пользователя есть НЕпринятые задачи.
    """
    async with session_scope() as s:
        rows = await s.execute(
            select(ProblemList.code)
            .join(Problem, Problem.list_id == ProblemList.id)
            .where(
                ProblemList.is_closed.is_(False),
                Problem.assignee == user_tg_id,
                Problem.status.in_([
                    ProblemStatus.IN_PROGRESS,
                    ProblemStatus.REPORT_SENT,
                    ProblemStatus.REJECTED,
                ]),
            )
            .distinct()
            .order_by(ProblemList.code)
        )
        return [r[0] for r in rows.all()]


async def _load_problems_for_user(list_code: str, user_tg_id: int) -> list[dict]:
    """
    Возвращает активные проблемы (без принятых) в указанном списке для данного пользователя.
    """
    async with session_scope() as s:
        rows = await s.execute(
            select(
                Problem.number,
                Problem.title,
                Problem.status,
            )
            .join(ProblemList)
            .where(
                ProblemList.code == list_code,
                Problem.assignee == user_tg_id,
                Problem.status.in_([
                    ProblemStatus.IN_PROGRESS,
                    ProblemStatus.REPORT_SENT,
                    ProblemStatus.REJECTED,
                ]),
            )
            .order_by(Problem.number)
        )
    problems = []
    for num, title, status in rows.all():
        problems.append(
            {"number": num, "title": title, "status": status}
        )
    return problems


async def _show_problems_in_list(msg: Message, list_code: str, user_tg_id: int):
    """Редактирует сообщение, показывая список проблем пользователя в выбранном списке."""
    problems = await _load_problems_for_user(list_code, user_tg_id)

    if not problems:
        await msg.edit_text(
            f"В списке <b>{list_code}</b> нет задач, назначенных на вас.",
            reply_markup=lists_menu([list_code]),
        )
        return

    lines = [f"Список: <b>{list_code}</b>", "", "Ваши проблемы:"]
    for p in problems:
        status_label = STATUS_LABELS.get(p["status"], str(p["status"]))
        lines.append(f"#{p['number']} — {p['title']} [{status_label}]")

    await msg.edit_text(
        "\n".join(lines),
        reply_markup=problems_menu(list_code, problems),
    )


async def _load_problem_detail(list_code: str, number: int) -> dict | None:
    """
    Подробности проблемы: id, title, status, due_date, note, assignee, is_closed.
    """
    async with session_scope() as s:
        rows = await s.execute(
            select(
                Problem.id,
                Problem.title,
                Problem.status,
                Problem.due_date,
                Problem.note,
                Problem.assignee,
                ProblemList.is_closed,
            )
            .join(ProblemList)
            .where(
                ProblemList.code == list_code,
                Problem.number == number,
            )
            .limit(1)
        )
        row = rows.first()
    if not row:
        return None

    pid, title, status, due, note, assignee, is_closed = row
    return {
        "id": pid,
        "title": title,
        "status": status,
        "due_date": due,
        "note": note,
        "assignee": assignee,
        "is_closed": bool(is_closed),
    }


# ===== /start =====

@user_router.message(F.text == "/start")
async def cmd_start(msg: Message, state: FSMContext, event_from_user_role: str | None = None):
    if not await guard_user(msg, event_from_user_role):
        return
    await state.clear()
    ensure_dirs()
    async with session_scope() as s:
        await get_or_create_user(
            s,
            tg_id=msg.from_user.id,
            username=msg.from_user.username,
            first_name=msg.from_user.first_name,
            last_name=msg.from_user.last_name,
        )
    await msg.answer(START, reply_markup=main_menu())


# ===== Главное меню: список проблем =====

@user_router.callback_query(F.data == "user:problems")
async def cb_problems_root(call: CallbackQuery, state: FSMContext, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return
    await state.clear()

    codes = await _load_user_lists(call.from_user.id)

    if not codes:
        await call.message.edit_text(
            "У вас нет назначенных задач в открытых списках.",
            reply_markup=main_menu(),
        )
        await call.answer()
        return

    if len(codes) == 1:
        # сразу показываем проблемы этого списка
        await _show_problems_in_list(call.message, codes[0], call.from_user.id)
    else:
        await call.message.edit_text(
            "Выберите список проблем:",
            reply_markup=lists_menu(codes),
        )

    await call.answer()


@user_router.callback_query(F.data == "user:back_main")
async def cb_back_main(call: CallbackQuery, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return
    await call.message.edit_text(START, reply_markup=main_menu())
    await call.answer()


@user_router.callback_query(F.data == "user:back_lists")
async def cb_back_lists(call: CallbackQuery, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return
    codes = await _load_user_lists(call.from_user.id)
    if not codes:
        await call.message.edit_text(
            "У вас нет назначенных задач в открытых списках.",
            reply_markup=main_menu(),
        )
    else:
        await call.message.edit_text(
            "Выберите список проблем:",
            reply_markup=lists_menu(codes),
        )
    await call.answer()


# ===== Показ одного списка проблем =====

@user_router.callback_query(F.data.startswith("user:plist_view:"))
async def cb_view_list(call: CallbackQuery, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return
    list_code = call.data.split(":", 2)[2]
    await _show_problems_in_list(call.message, list_code, call.from_user.id)
    await call.answer()


@user_router.callback_query(F.data.startswith("user:back_problems:"))
async def cb_back_problems(call: CallbackQuery, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return
    list_code = call.data.split(":", 2)[2]
    await _show_problems_in_list(call.message, list_code, call.from_user.id)
    await call.answer()


# ===== Карточка проблемы =====

@user_router.callback_query(F.data.startswith("user:prob:"))
async def cb_problem_detail(call: CallbackQuery, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return

    _, _, list_code, num_s = call.data.split(":", 3)
    number = int(num_s)

    p = await _load_problem_detail(list_code, number)
    if not p:
        await call.message.edit_text("Эта проблема не найдена.")
        await call.answer()
        return

    # только назначенный исполнитель видит карточку
    if p["assignee"] is not None and p["assignee"] != call.from_user.id:
        await call.message.edit_text("Эта проблема назначена на другого исполнителя.")
        await call.answer()
        return

    status_label = STATUS_LABELS.get(p["status"], str(p["status"]))
    title = p["title"] or "(без названия)"
    due = p["due_date"] or ""
    note = p["note"] or ""

    lines = [
        f"Список: <b>{list_code}</b>",
        f"Проблема №{number}",
        f"Название: {title}",
        f"Статус: {status_label}",
    ]
    if due:
        lines.append(f"Срок: {due}")
    if note:
        lines.append("")
        lines.append(f"Примечание администратора:\n{note}")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=problem_detail_menu(list_code, number),
    )
    await call.answer()


# ===== Запуск загрузки отчёта из карточки проблемы =====

@user_router.callback_query(F.data.startswith("user:upload_for:"))
async def cb_upload_for_problem(call: CallbackQuery, state: FSMContext, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return

    _, _, list_code, num_s = call.data.split(":", 3)
    number = int(num_s)

    p = await _load_problem_detail(list_code, number)
    if not p:
        await call.message.edit_text("Эта проблема не найдена.")
        await call.answer()
        return

    if p["is_closed"]:
        await call.message.edit_text("⛔ Список закрыт. Отчёты по этой проблеме не принимаются.")
        await call.answer()
        return

    if p["assignee"] is not None and p["assignee"] != call.from_user.id:
        await call.message.edit_text("⛔ Отчёт по этой проблеме может отправить только назначенный исполнитель.")
        await call.answer()
        return

    await state.update_data(
        problem_id=int(p["id"]),
        problem_number=number,
        list_code=list_code,
    )
    await state.set_state(ReportStates.waiting_payload)

    await call.message.edit_text(
        f"Вы выбрали проблему №{number} из списка <b>{list_code}</b>.\n\n{ASK_DATA}"
    )
    await call.answer()


# ===== Приём любого контента как отчёта =====

@user_router.message(ReportStates.waiting_payload)
async def receive_anything(msg: Message, state: FSMContext, event_from_user_role: str | None = None):
    if not await guard_user(msg, event_from_user_role):
        await state.clear()
        return

    data = await state.get_data()
    problem_id = int(data.get("problem_id"))
    problem_number = int(data.get("problem_number"))
    list_code = data.get("list_code")

    # зарегистрируем пользователя и создадим Report
    async with session_scope() as s:
        user = await get_or_create_user(
            s,
            tg_id=msg.from_user.id,
            username=msg.from_user.username,
            first_name=msg.from_user.first_name,
            last_name=msg.from_user.last_name,
        )
        report = await create_report(
            s,
            user_id=user.id,
            problem_id=problem_id,
            user_chat_id=msg.chat.id,
            user_msg_id=msg.message_id,
        )
        report_id = report.id
        # статус проблемы -> REPORT_SENT
        await set_problem_status(s, problem_id, ProblemStatus.REPORT_SENT)

    caption = (getattr(msg, "caption", None) or msg.text or "").strip()

    async def handle_content(file_id: str | None, kind: MediaType, filename: str):
        file = await msg.bot.get_file(file_id) if file_id else None
        if file:
            raw = await msg.bot.download_file(file.file_path)
            content = raw.read()
        else:
            content = (caption or "").encode("utf-8")

        p1, p2, p3 = build_paths(problem_id, msg.from_user.id, report_id, filename)
        save_bytes_to_all((p1, p2, p3), content)

        async with session_scope() as s:
            await add_media(
                s,
                report_id=report_id,
                kind=kind,
                file_id=file_id,
                file_path=str(p1),
                caption=caption if caption else None,
            )

    # определяем тип контента
    if msg.photo:
        photo = msg.photo[-1]
        await handle_content(photo.file_id, MediaType.PHOTO, f"photo_{photo.file_unique_id}.jpg")
    elif msg.video:
        await handle_content(msg.video.file_id, MediaType.VIDEO, f"video_{msg.video.file_unique_id}.mp4")
    elif msg.document:
        await handle_content(
            msg.document.file_id,
            MediaType.DOCUMENT,
            msg.document.file_name or f"document_{msg.document.file_unique_id}",
        )
    elif msg.audio:
        await handle_content(
            msg.audio.file_id,
            MediaType.AUDIO,
            msg.audio.file_name or f"audio_{msg.audio.file_unique_id}.mp3",
        )
    elif msg.voice:
        await handle_content(msg.voice.file_id, MediaType.VOICE, f"voice_{msg.voice.file_unique_id}.ogg")
    elif msg.text:
        await handle_content(None, MediaType.TEXT, "message.txt")
    else:
        await handle_content(None, MediaType.OTHER, "payload.bin")

    # ===== общий текст для админов и группы =====
    user_caption = caption or ""
    info_block = (
        f"Новый отчёт #{report_id}\n"
        f"Список: {list_code}\n"
        f"Проблема №{problem_number}\n"
        f"От пользователя: {msg.from_user.id}"
    )
    if user_caption:
        admin_caption = info_block + f"\n\nПодпись пользователя:\n{user_caption}"
    else:
        admin_caption = info_block

    # ===== нотифицируем админов =====
    async with session_scope() as s:
        admins = (
            await s.execute(
                select(MUser.id).where(MUser.role == Role.ADMIN)
            )
        ).scalars().all()

    for admin_id in admins:
        try:
            await msg.copy_to(
                chat_id=admin_id,
                caption=admin_caption,
                reply_markup=review_kb(report_id, msg.from_user.id),
            )
        except Exception:
            pass

    # ===== дублируем отчёт в тему группы (уже существующую) =====
    try:
        topic_id = await _get_group_topic_for_list(list_code)
        if topic_id:
            # в группу отправляем без кнопок модерации
            await msg.copy_to(
                chat_id=GROUP_CHAT_ID,
                message_thread_id=topic_id,
                caption=admin_caption,
            )
    except Exception:
        # если нет прав/тем или GROUP_CHAT_ID неверный – просто промолчим
        pass

    await msg.answer(REPORT_SENT, reply_markup=main_menu())
    await state.clear()


# ===== Статистика пользователя =====

@user_router.callback_query(F.data == "user:stats")
async def cb_stats(call: CallbackQuery, event_from_user_role: str | None = None):
    if not await guard_user(call, event_from_user_role):
        return

    async with session_scope() as s:
        st = await user_stats(s, call.from_user.id)

    new_text = USER_STATS.format(**st)

    # если сообщение уже с таким же текстом – не редактируем
    current_text = call.message.text or call.message.caption or ""

    if current_text == new_text:
        # просто ответим на callback, чтобы убрать "часики"
        await call.answer("Статистика уже актуальна ✅", show_alert=False)
        return

    try:
        # если это обычный текст – edit_text
        if call.message.text is not None:
            await call.message.edit_text(new_text, reply_markup=main_menu())
        else:
            # вдруг это было медиа с подписью
            await call.message.edit_caption(new_text, reply_markup=main_menu())
    except TelegramBadRequest as e:
        # на всякий случай гасим "message is not modified", если вдруг Telegram решит ещё раз придраться
        if "message is not modified" not in str(e):
            raise

    await call.answer("Обновлено ✅", show_alert=False)