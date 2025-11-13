
from __future__ import annotations
from typing import Iterable, Optional
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

async def upsert_problems(
    session: AsyncSession,
    list_code: str,
    list_code_file: str,
    rows: list[dict],
) -> ProblemList:
    """
    Обновляет/создаёт список проблем и его проблемы по данным из файла.

    list_code — код списка (берём из имени файла)
    rows      — список dict'ов:
                {"number", "title", "assignee", "due_date"}
    Возвращает ProblemList.
    """
    # находим или создаём сам список
    result = await session.execute(
        select(ProblemList).where(ProblemList.code == list_code)
    )
    plist: ProblemList | None = result.scalar_one_or_none()

    if plist is None:
        plist = ProblemList(code=list_code, title=list_code_file)
        session.add(plist)
        await session.flush()  # чтобы получить id

    for r in rows:
        number = int(r["number"])
        title = r.get("title") or ""
        assignee = r.get("assignee")
        due_date = r.get("due_date")

        # ищем проблему внутри этого списка
        result = await session.execute(
            select(Problem).where(
                Problem.list_id == plist.id,
                Problem.number == number,
            )
        )
        prob: Problem | None = result.scalar_one_or_none()

        if prob is None:
            prob = Problem(
                list_id=plist.id,
                number=number,
                status=ProblemStatus.IN_PROGRESS,
            )
            session.add(prob)

        prob.title = title
        prob.assignee = assignee
        prob.due_date = due_date

    await session.commit()
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
    q = await session.execute(
        select(
            Problem.status,
            func.count(Problem.id)
        )
        .where(Problem.assignee == tg_id)
        .group_by(Problem.status)
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
) -> List[Tuple[Problem, date, int]]:
    """
    Возвращает список (problem, due_date, days_left) для напоминаний.

    Условие:
      - список не закрыт (ProblemList.is_closed = False)
      - есть assignee (Telegram ID)
      - есть due_date (в формате 'YYYY-MM-DD')
      - статус проблемы: IN_PROGRESS или REPORT_SENT
      - days_left в [0, 1, 2, 3]
    """
    stmt = (
        select(Problem, ProblemList)
        .join(ProblemList, Problem.list_id == ProblemList.id)
        .where(
            ProblemList.is_closed.is_(False),
            Problem.assignee.isnot(None),
            Problem.due_date.isnot(None),
            Problem.status.in_([ProblemStatus.IN_PROGRESS, ProblemStatus.REPORT_SENT]),
        )
    )
    res = await session.execute(stmt)
    rows = res.all()

    out: List[Tuple[Problem, date, int]] = []

    for prob, plist in rows:
        try:
            # due_date у тебя String(32) — считаем, что формат YYYY-MM-DD
            d = datetime.strptime(prob.due_date.strip(), "%Y-%m-%d").date()
        except Exception:
            # если дата кривая — просто пропускаем
            continue

        days_left = (d - today).days
        if 0 <= days_left <= 3:
            out.append((prob, d, days_left))

    return out

