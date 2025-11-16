import os
from datetime import date, datetime

from aiogram import Bot
from aiogram.types import FSInputFile
from docxtpl import DocxTemplate
from sqlalchemy import select, or_

from db import session_scope
from crud import get_problems_for_reminder
from keyboards.admin_main_kb import admin_main_menu
from models import Staff, ActEntry, Problem, ProblemList, ProblemStatus


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


async def cb_admin_create_akt_by_staff(
    bot: Bot
):
    """
    Формирует акты по сотрудникам из таблицы Staff.

    Для каждого staff.assignee:
      - ищем проблемы со статусом ACCEPTED
      - у которых assignees_raw начинается с этого ID (0-й индекс)
      - и по которым ЕЩЁ НЕТ записи в Acts (ActEntry)
      - подгружаем ProblemList (code, title)
      - собираем один акт на сотрудника с его задачами
      - после генерации записываем ActEntry, чтобы второй раз не брать.
    """

    # папка для временных файлов
    os.makedirs("temp", exist_ok=True)
    doc_path = "shablon/akt.docx"

    total_acts = 0

    async with session_scope() as s:
        # 1) Берём всех сотрудников
        staff_rows = (
            await s.execute(select(Staff).order_by(Staff.fio))
        ).scalars().all()

        for staff in staff_rows:
            tg_id = staff.assignee

            # --- подзапрос: есть ли уже акт по этой задаче и этому исполнителю
            act_exists = (
                select(ActEntry.id)
                .where(
                    ActEntry.problem_id == Problem.id,
                    ActEntry.assignee == tg_id,
                )
                .exists()
            )

            # 2) Ищем задачи, где этот tg_id стоит ПЕРВЫМ в assignees_raw
            #    и статус == ACCEPTED
            #    и для них ещё нет записи в Acts
            stmt = (
                select(Problem, ProblemList)
                .join(ProblemList, Problem.list_id == ProblemList.id)
                .where(
                    Problem.status == ProblemStatus.ACCEPTED,
                    Problem.assignees_raw.isnot(None),
                    or_(
                        Problem.assignees_raw == str(tg_id),
                        Problem.assignees_raw.like(f"{tg_id},%"),
                    ),
                    ~act_exists,  # <<< акт ещё не формировался
                )
                .order_by(ProblemList.code, Problem.number)
            )
            rows = (await s.execute(stmt)).all()

            if not rows:
                continue  # у этого сотрудника нет новых принятых задач – пропускаем

            # 3) Собираем текст для {{data}}
            lines: list[str] = []
            for prob, plist in rows:
                lines.append(
                    f"№{prob.number}"
                )
            data_text = ", ".join(lines)

            # 4) Берём данные ProblemList (из первого списка в выборке)
            first_plist: ProblemList = rows[0][1]
            list_title = first_plist.title or first_plist.code
            list_code = first_plist.code

            # 4) Готовим контекст для шаблона
            context = {
                "title": list_title,       # подгони под свой шаблон
                "data": data_text,
                "post": staff.post,
                "fio": staff.fio,
            }

            # 5) Рендерим docx по шаблону
            try:
                doc = DocxTemplate(doc_path)
            except Exception as e:
                print(f"❌ Не удалось открыть шаблон акта: {e}")
                return

            doc.render(context)

            # имя файла: akt_<fio_or_id>.docx
            safe_fio = (staff.fio or str(tg_id)).replace(" ", "_")
            filename = f"akt_{list_code}_{safe_fio}.docx"
            out_path = os.path.join("temp", filename)

            doc.save(out_path)
            total_acts += 1

            # 6) Запоминаем, что по этим задачам и этому исполнителю акт уже сформирован
            for prob, _plist in rows:
                s.add(
                    ActEntry(
                        problem_id=prob.id,
                        assignee=tg_id,
                    )
                )

            # можно коммитить пачками, но одного в конце контекста обычно достаточно.
            # я добавлю явный коммит после цикла по staff.
            await bot.send_document(chat_id=tg_id,
                document=FSInputFile(out_path),
                caption=f"Акт для {staff.fio or tg_id}",
            )

        # фиксируем все ActEntry
        await s.commit()