from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    group: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    inactive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    favorite_1: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    favorite_2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    favorite_3: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(10), index=True, nullable=False)   # 'DD.MM'
    group: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    lesson_number: Mapped[int] = mapped_column(Integer, nullable=False)
    time: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    subject: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    room: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    teacher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class KnownSchedule(Base):
    __tablename__ = "known_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date_folder: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
