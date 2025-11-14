
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Optional, List
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, relationship
from sqlalchemy import ForeignKey, String, DateTime, Enum, Integer, Text, UniqueConstraint, BigInteger, Boolean


class Base(DeclarativeBase): pass

class Role(StrEnum):
    USER="user"; ADMIN="admin"

class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    role: Mapped[Role]=mapped_column(Enum(Role),default=Role.USER)
    username: Mapped[Optional[str]]=mapped_column(String(64))
    first_name: Mapped[Optional[str]]=mapped_column(String(128))
    last_name: Mapped[Optional[str]]=mapped_column(String(128))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    reports: Mapped[List["Report"]]=relationship(back_populates="user",foreign_keys="Report.user_id",cascade="all, delete-orphan")
    moderated_reports: Mapped[List["Report"]]=relationship(back_populates="admin",foreign_keys="Report.admin_id")

class ProblemList(Base):
    __tablename__ = "problem_lists"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 👇 тема в группе (message_thread_id форума)
    group_topic_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    problems: Mapped[list["Problem"]] = relationship(
        back_populates="plist",
        cascade="all, delete-orphan",
    )

class ProblemStatus(StrEnum):
    IN_PROGRESS   = "in_progress"      # 1. в работе
    REPORT_SENT   = "report_sent"      # 2. отправлен отчет
    ACCEPTED      = "accepted"         # 3. отчет принят
    REJECTED      = "rejected"         # 4. отчет отклонен

class Problem(Base):
    __tablename__ = "problems"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("problem_lists.id"))
    number: Mapped[int] = mapped_column(Integer)                              # номер в списке
    title: Mapped[str] = mapped_column(Text)
    # assignee: Mapped[int | None] = mapped_column(BigInteger)                  # TG id
    assignees_raw: Mapped[str | None] = mapped_column("assignees", Text, nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[ProblemStatus] = mapped_column(Enum(ProblemStatus), default=ProblemStatus.IN_PROGRESS)  # <-- статус
    note: Mapped[str | None] = mapped_column(Text)                            # <-- примечание (причина отклонения)

    plist: Mapped["ProblemList"] = relationship(back_populates="problems")
    reports: Mapped[List["Report"]] = relationship(back_populates="problem")

    __table_args__ = (UniqueConstraint("list_id", "number", name="uix_problem_list_number"),)

    # Удобное свойство: список ID
    @property
    def assignees(self) -> list[int]:
        if not self.assignees_raw:
            return []
        ids: list[int] = []
        for part in self.assignees_raw.split(","):
            p = part.strip()
            if not p:
                continue
            try:
                ids.append(int(p))
            except ValueError:
                continue
        return ids

    @assignees.setter
    def assignees(self, values: list[int] | None) -> None:
        if not values:
            self.assignees_raw = None
        else:
            self.assignees_raw = ",".join(str(v) for v in values)

class ReportStatus(StrEnum):
    PENDING="pending"; ACCEPTED="accepted"; REJECTED="rejected"

class Report(Base):
    __tablename__="reports"
    id: Mapped[int]=mapped_column(primary_key=True,autoincrement=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    problem_id: Mapped[int]=mapped_column(ForeignKey("problems.id"))
    user_chat_id: Mapped[int]=mapped_column(Integer)
    user_msg_id: Mapped[int]=mapped_column(Integer)
    status: Mapped[ReportStatus]=mapped_column(Enum(ReportStatus),default=ReportStatus.PENDING)
    admin_reason: Mapped[Optional[str]]=mapped_column(Text)
    admin_id: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    user: Mapped["User"]=relationship(back_populates="reports",foreign_keys=[user_id])
    admin: Mapped[Optional["User"]]=relationship(back_populates="moderated_reports",foreign_keys=[admin_id])
    problem: Mapped["Problem"]=relationship(back_populates="reports")
    media: Mapped[List["ReportMedia"]]=relationship(back_populates="report",cascade="all, delete-orphan")
class MediaType(StrEnum):
    PHOTO="photo"; VIDEO="video"; DOCUMENT="document"; TEXT="text"; AUDIO="audio"; VOICE="voice"; OTHER="other"
class ReportMedia(Base):
    __tablename__="report_media"
    id: Mapped[int]=mapped_column(primary_key=True,autoincrement=True)
    report_id: Mapped[int]=mapped_column(ForeignKey("reports.id"))
    kind: Mapped[MediaType]=mapped_column(Enum(MediaType))
    file_id: Mapped[Optional[str]]=mapped_column(String(256))
    file_path: Mapped[Optional[str]]=mapped_column(Text)
    caption: Mapped[Optional[str]]=mapped_column(Text)
    report: Mapped["Report"]=relationship(back_populates="media")
