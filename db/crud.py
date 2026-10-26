"""Функции доступа к БД. Все операции асинхронные, принимают готовую сессию."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import models


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- users ---

async def get_user(session: AsyncSession, telegram_id: int) -> Optional[models.User]:
    res = await session.execute(select(models.User).where(models.User.telegram_id == telegram_id))
    return res.scalar_one_or_none()


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> models.User:
    user = await get_user(session, telegram_id)
    if user is None:
        user = models.User(telegram_id=telegram_id, subscribed=True, inactive=False)
        session.add(user)
        await session.flush()
    return user


async def set_group(session: AsyncSession, telegram_id: int, group: str) -> None:
    user = await get_or_create_user(session, telegram_id)
    user.group = group


async def set_subscribed(session: AsyncSession, telegram_id: int, value: bool) -> None:
    user = await get_or_create_user(session, telegram_id)
    user.subscribed = value


async def mark_inactive(session: AsyncSession, telegram_id: int) -> None:
    user = await get_user(session, telegram_id)
    if user is not None:
        user.inactive = True


async def list_subscribed_users(session: AsyncSession) -> list[models.User]:
    res = await session.execute(
        select(models.User).where(
            models.User.subscribed.is_(True),
            models.User.inactive.is_(False),
            models.User.group.isnot(None),
        )
    )
    return list(res.scalars())


# ------------------------------------------------------------ favorites ---

FAVORITE_SLOTS = (1, 2, 3)


def _fav_attr(slot: int) -> str:
    if slot not in FAVORITE_SLOTS:
        raise ValueError(f"недопустимый слот избранного: {slot}")
    return f"favorite_{slot}"


async def get_favorites(session: AsyncSession, telegram_id: int) -> dict[int, Optional[str]]:
    """Возвращает {1: группа|None, 2: ..., 3: ...}."""
    user = await get_user(session, telegram_id)
    if user is None:
        return {slot: None for slot in FAVORITE_SLOTS}
    return {slot: getattr(user, _fav_attr(slot), None) for slot in FAVORITE_SLOTS}


async def set_favorite(session: AsyncSession, telegram_id: int, slot: int, group: str) -> None:
    user = await get_or_create_user(session, telegram_id)
    setattr(user, _fav_attr(slot), group)


async def clear_favorite(session: AsyncSession, telegram_id: int, slot: int) -> None:
    user = await get_or_create_user(session, telegram_id)
    setattr(user, _fav_attr(slot), None)


# ------------------------------------------------------------- schedule ---

async def get_groups(session: AsyncSession) -> list[str]:
    res = await session.execute(
        select(models.ScheduleEntry.group).distinct().order_by(models.ScheduleEntry.group)
    )
    return list(res.scalars())


async def get_schedule(session: AsyncSession, date: str, group: str) -> list[models.ScheduleEntry]:
    res = await session.execute(
        select(models.ScheduleEntry)
        .where(models.ScheduleEntry.date == date, models.ScheduleEntry.group == group)
        .order_by(models.ScheduleEntry.lesson_number)
    )
    return list(res.scalars())


async def replace_schedule(
    session: AsyncSession, date: str, group: str, lessons: list[dict]
) -> None:
    """Полностью заменяет расписание группы на дату (delete + insert)."""
    await session.execute(
        delete(models.ScheduleEntry).where(
            models.ScheduleEntry.date == date, models.ScheduleEntry.group == group
        )
    )
    for l in lessons:
        session.add(
            models.ScheduleEntry(
                date=date,
                group=group,
                lesson_number=l["lesson_number"],
                time=l.get("time", ""),
                subject=l.get("subject", ""),
                room=l.get("room", ""),
                teacher=l.get("teacher") or None,
            )
        )
    await session.flush()


async def delete_schedule_for_date(session: AsyncSession, date: str) -> None:
    await session.execute(delete(models.ScheduleEntry).where(models.ScheduleEntry.date == date))


# ---------------------------------------------------------------- known ---

async def get_known(session: AsyncSession, date_folder: str) -> Optional[models.KnownSchedule]:
    res = await session.execute(
        select(models.KnownSchedule).where(models.KnownSchedule.date_folder == date_folder)
    )
    return res.scalar_one_or_none()


async def mark_known(session: AsyncSession, date_folder: str, notified_at: Optional[datetime] = None) -> None:
    known = await get_known(session, date_folder)
    if known is None:
        known = models.KnownSchedule(date_folder=date_folder, notified_at=notified_at or _utcnow())
        session.add(known)
    else:
        known.notified_at = notified_at or _utcnow()
    await session.flush()


async def list_known(session: AsyncSession) -> list[models.KnownSchedule]:
    res = await session.execute(
        select(models.KnownSchedule).order_by(models.KnownSchedule.date_folder)
    )
    return list(res.scalars())
