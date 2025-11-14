
from __future__ import annotations
from typing import Iterable, Optional, Dict, Any
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from models import User, Role, Problem, Report, ReportStatus, ReportMedia, MediaType, ProblemList, ProblemStatus
from typing import List, Tuple
from datetime import datetime, date

async def get_or_create_user(session: AsyncSession, *, tg_id: int, username: str | None, first_name: str | None, last_name: str | None) -> User:
    user = await session.get(User, tg_id)
    if not user:
        user = User(id=tg_id, username=username, first_name=first_name, last_name=last_name)
        session.add(user)
    return user

async def ensure_bootstrap_admins(session: AsyncSession, ids: list[int]):
    for i in ids:
        user = await session.get(User, i)
        if not user:
            user = User(id=i, role=Role.ADMIN)
            session.add(user)
        else:
            user.role = Role.ADMIN

async def is_admin(session: AsyncSession, tg_id: int) -> bool:
    u = await session.get(User, tg_id)
    return bool(u and u.role == Role.ADMIN)

async def set_admin(session: AsyncSession, tg_id: int, make_admin: bool):
    u = await session.get(User, tg_id)
    if not u:
        u = User(id=tg_id)
        session.add(u)
    u.role = Role.ADMIN if make_admin else Role.USER

async def get_or_create_problem_list(session: AsyncSession, code: str, title: str | None = None) -> ProblemList:
    q = await session.execute(select(ProblemList).where(ProblemList.code == code))
    pl = q.scalar_one_or_none()
    if not pl:
        pl = ProblemList(code=code, title=title or code)
        session.add(pl)
        await session.flush()
    return pl

async def list_problem_lists(session: AsyncSession, *, only_open: bool = False) -> list[ProblemList]:
    q = select(ProblemList).order_by(ProblemList.code)
    if only_open:
        q = q.where(ProblemList.is_closed.is_(False))
    return (await session.execute(q)).scalars().all()


def assignees_to_str(lst: list[int]) -> str:
    return ",".join(str(x) for x in lst)

def assignees_from_str(s: str | None) -> list[int]:
    if not s:
        return []
    out = []
    for part in s.split(","):
        part = part.strip()
        try:
            out.append(int(part))
        except:
            pass
    return out

async def upsert_problems(
    session: AsyncSession,
    list_code: str,
    rows: List[Dict[str, Any]],
    list_title: str | None = None,
) -> ProblemList:
    """
    Создаёт или обновляет список проблем с кодом `list_code`.

    rows — это список dict от parse_problems_xlsx / parse_problems_csv:
        {
            "number": int,
            "title": str,
            "assignees": list[int],
            "due_date": str | None,
        }

    Поведение:
      - если ProblemList с таким code нет — создаём;
      - для каждой строки обновляем/создаём Problem с этим list_id и number;
      - статусы Problem НЕ трогаем (чтобы не сбрасывать принятые/отклонённые).
    """

    # 1. Ищем (или создаём) ProblemList
    res_pl = await session.execute(
        select(ProblemList).where(ProblemList.code == list_code)
    )
    plist = res_pl.scalar_one_or_none()

    if plist is None:
        plist = ProblemList(
            code=list_code,
            title=list_title or list_code,
            is_closed=False,
        )
        session.add(plist)
        # нужен flush, чтобы появился plist.id для ForeignKey
        await session.flush()

    # 2. Загружаем уже существующие проблемы этого списка
    res_probs = await session.execute(
        select(Problem).where(Problem.list_id == plist.id)
    )
    existing: dict[int, Problem] = {p.number: p for p in res_probs.scalars().all()}

    # 3. Обрабатываем строки из файла
    for r in rows:
        try:
            number = int(r["number"])
        except (KeyError, TypeError, ValueError):
            continue

        title = (r.get("title") or "").strip()
        assignees: list[int] = r.get("assignees") or []
        due_date = r.get("due_date")
        if isinstance(due_date, str):
            due_date = due_date.strip() or None

        prob = existing.get(number)

        if prob is None:
            # создаём новую задачу
            prob = Problem(
                list_id=plist.id,
                number=number,
                status=ProblemStatus.IN_PROGRESS,
            )
            session.add(prob)
            existing[number] = prob

        # обновляем поля
        if title:
            prob.title = title
        # тут предполагается, что в модели Problem есть
        # property assignees/assignees_raw как мы делали ранее
        prob.assignees = assignees
        prob.due_date = due_date

    # коммит снаружи или здесь — на твой вкус
    # здесь можно не коммитить, если выше ты делаешь session.commit()
    return plist

async def get_problem_by_list_and_number(session: AsyncSession, list_code: str, number: int) -> dict | None:
    q = await session.execute(
        select(
            Problem.id,
            Problem.assignee,
            Problem.number,
            ProblemList.is_closed,
        ).join(ProblemList)
         .where(ProblemList.code == list_code, Problem.number == number)
         .limit(1)
    )
    row = q.first()
    if not row:
        return None
    pid, assignee, num, is_closed = row
    return {
        "id": pid,
        "assignee": assignee,
        "number": num,
        "is_closed": bool(is_closed),
    }

async def set_problem_status(session: AsyncSession, problem_id: int, status: ProblemStatus, note: str | None = None):
    p = await session.get(Problem, problem_id)
    if not p:
        return False
    p.status = status
    if note is not None:
        p.note = note
    return True

async def close_list_if_completed(session: AsyncSession, list_id: int):
    # Закрываем список, если ВСЕ проблемы в нём имеют статус ACCEPTED
    total = (await session.execute(select(func.count(Problem.id)).where(Problem.list_id == list_id))).scalar() or 0
    accepted = (await session.execute(select(func.count(Problem.id)).where(Problem.list_id == list_id, Problem.status == ProblemStatus.ACCEPTED))).scalar() or 0
    pl = await session.get(ProblemList, list_id)
    if total > 0 and accepted == total and pl and not pl.is_closed:
        pl.is_closed = True
        from datetime import datetime
        pl.closed_at = datetime.utcnow()

async def get_problem(session: AsyncSession, pid: int) -> Optional[Problem]:
    return await session.get(Problem, pid)

async def create_report(session: AsyncSession, *, user_id: int, problem_id: int, user_chat_id: int, user_msg_id: int) -> Report:
    r = Report(user_id=user_id, problem_id=problem_id, user_chat_id=user_chat_id, user_msg_id=user_msg_id)
    session.add(r); await session.flush(); return r

async def set_report_status(session: AsyncSession, report_id: int, status: ReportStatus, admin_id: int, reason: str | None = None):
    r = await session.get(Report, report_id)
    if not r: return False
    r.status = status; r.admin_id = admin_id; r.admin_reason = reason; return True

async def add_media(session: AsyncSession, *, report_id: int, kind: MediaType, file_id: str | None, file_path: str | None, caption: str | None):
    m = ReportMedia(report_id=report_id, kind=kind, file_id=file_id, file_path=file_path, caption=caption); session.add(m)

async def user_stats(session: AsyncSession, tg_id: int) -> dict:
    """
    Статистика по ЗАДАЧАМ для исполнителя с данным Telegram ID.
    Считаем каждую проблему один раз по её текущему статусу.
    """

    pattern = f"%,{tg_id},%"

    q = await session.execute(
        select(
            Problem.status,
            func.count(Problem.id)
        ).where(
            Problem.assignees_raw.is_not(None),
            ("," + Problem.assignees_raw + ",").like(pattern),
        ).group_by(Problem.status)
    )
    rows = q.all()

    by_status: dict[ProblemStatus, int] = {status: cnt for status, cnt in rows}

    in_progress = by_status.get(ProblemStatus.IN_PROGRESS, 0)
    sent        = by_status.get(ProblemStatus.REPORT_SENT, 0)
    accepted    = by_status.get(ProblemStatus.ACCEPTED, 0)
    rejected    = by_status.get(ProblemStatus.REJECTED, 0)

    total = in_progress + sent + accepted + rejected

    return {
        "total": total,
        "in_progress": in_progress,
        "sent": sent,
        "accepted": accepted,
        "rejected": rejected,
    }

async def problems_stats(session: AsyncSession) -> list[dict]:
    q = (select(Problem.id, Problem.title, func.count(Report.id), func.sum(case((Report.status == ReportStatus.ACCEPTED, 1), else_=0)), func.sum(case((Report.status == ReportStatus.REJECTED, 1), else_=0)))
         .join(Report, Report.problem_id == Problem.id, isouter=True).group_by(Problem.id).order_by(Problem.id))
    res = []
    for pid, title, total, acc, rej in (await session.execute(q)).all():
        res.append({"problem_id": pid, "title": title, "total": int(total or 0), "accepted": int(acc or 0), "rejected": int(rej or 0)})
    return res


async def get_problems_for_reminder(
    session: AsyncSession,
    today: date,
) -> List[Dict[str, Any]]:
    """
    Возвращает список словарей для напоминаний.

    Каждый элемент:
      {
          "problem_id": int,
          "number": int,
          "title": str,
          "due_date": date,
          "days_left": int,
          "assignees": list[int],
          "plist_title": str,
          "plist_code": str,
      }

    Условия:
      - список не закрыт (ProblemList.is_closed = False)
      - есть исполнители (assignees_raw не NULL)
      - есть due_date (строка в формате 'YYYY-MM-DD')
      - статус: IN_PROGRESS или REPORT_SENT
      - days_left в [0, 1, 2, 3]
    """
    stmt = (
        select(Problem, ProblemList.title, ProblemList.code)
        .join(ProblemList, Problem.list_id == ProblemList.id)
        .where(
            ProblemList.is_closed.is_(False),
            Problem.assignees_raw.isnot(None),
            Problem.due_date.isnot(None),
            Problem.status.in_([
                ProblemStatus.IN_PROGRESS,
                ProblemStatus.REPORT_SENT,
            ]),
        )
    )

    res = await session.execute(stmt)
    rows = res.all()  # [(Problem, title, code), ...]

    result: List[Dict[str, Any]] = []

    for prob, plist_title, plist_code in rows:
        # разбор due_date
        try:
            d = datetime.strptime(prob.due_date.strip(), "%Y-%m-%d").date()
        except Exception:
            # кривая дата — пропускаем
            continue

        days_left = (d - today).days
        if not (0 <= days_left <= 3):
            continue

        # здесь ещё есть активная сессия, можно спокойно дернуть prob.assignees
        assignees = prob.assignees  # свойство из модели (список int)

        if not assignees:
            # если в итоге пусто — нет, кому напоминать
            continue

        result.append(
            {
                "problem_id": prob.id,
                "number": prob.number,
                "title": prob.title,
                "due_date": d,
                "days_left": days_left,
                "assignees": assignees,
                "plist_title": plist_title,
                "plist_code": plist_code,
            }
        )

    return result
