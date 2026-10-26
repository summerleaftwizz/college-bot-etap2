import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from db import SessionLocal
from db import crud
from keyboards.groups import build_groups_keyboard
from keyboards.menu import (
    BTN_NOW,
    BTN_SCHEDULE,
    BTN_TODAY,
    BTN_TOMORROW,
    build_main_menu,
)
from services import formatting, watcher
from utils import now, today_ddmm, tomorrow_ddmm, week_days

logger = logging.getLogger(__name__)
router = Router()

SCHEDULE_INFO_TEXT = (
    "📖 <b>Расписание</b>\n\n"
    "Жми кнопки внизу:\n"
    "📅 <b>Сегодня</b> — пары на сегодня\n"
    "📅 <b>Завтра</b> — пары на завтра\n"
    "🔔 <b>Что сейчас</b> — идёт ли пара прямо сейчас\n\n"
    "Сменить группу можно в разделе 👤 <b>Профиль</b>."
)


async def _get_group(telegram_id: int) -> str | None:
    async with SessionLocal() as session:
        user = await crud.get_user(session, telegram_id)
        return user.group if user else None


async def _require_group(message: Message) -> str | None:
    group = await _get_group(message.from_user.id)
    if not group:
        await message.answer("Сначала выбери группу: /start")
    return group


async def _load(date: str, group: str):
    async with SessionLocal() as session:
        return await crud.get_schedule(session, date, group)


async def _send(message: Message, text: str, *, menu: bool = False) -> None:
    for chunk in formatting.split_message(text):
        await message.answer(
            chunk,
            parse_mode="HTML",
            reply_markup=build_main_menu() if menu else None,
        )


async def _force_load_if_empty(label: str, group: str, bot: Bot):
    entries = await _load(label, group)
    if not entries:
        try:
            await watcher.run_check(bot)
        except Exception:
            logger.exception("ошибка принудительной загрузки расписания")
        entries = await _load(label, group)
    return entries


# --- команды ---------------------------------------------------------------


@router.message(Command("today"))
async def cmd_today(message: Message, bot: Bot) -> None:
    group = await _require_group(message)
    if not group:
        return
    label = today_ddmm()
    entries = await _force_load_if_empty(label, group, bot)
    text = formatting.format_schedule(
        label, group, entries, now=now(), with_state=True, empty_text="Сегодня пар нет 🎉"
    )
    await _send(message, text)


@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message) -> None:
    group = await _require_group(message)
    if not group:
        return
    label = tomorrow_ddmm()
    entries = await _load(label, group)
    text = formatting.format_schedule(
        label, group, entries, now=now(), with_state=False, empty_text="Завтра пар нет 🎉"
    )
    await _send(message, text)


# --- кнопки главного меню (реагируют на ТЕКСТ кнопки) -----------------------


@router.message(F.text == BTN_TODAY)
async def btn_today(message: Message, bot: Bot) -> None:
    group = await _require_group(message)
    if not group:
        return
    label = today_ddmm()
    entries = await _force_load_if_empty(label, group, bot)
    text = formatting.format_schedule(
        label, group, entries, now=now(), with_state=True, empty_text="Сегодня пар нет 🎉"
    )
    await _send(message, text, menu=True)


@router.message(F.text == BTN_TOMORROW)
async def btn_tomorrow(message: Message) -> None:
    group = await _require_group(message)
    if not group:
        return
    label = tomorrow_ddmm()
    entries = await _load(label, group)
    text = formatting.format_schedule(
        label, group, entries, now=now(), with_state=False, empty_text="Завтра пар нет 🎉"
    )
    await _send(message, text, menu=True)


@router.message(F.text == BTN_NOW)
async def btn_now(message: Message, bot: Bot) -> None:
    group = await _require_group(message)
    if not group:
        return
    label = today_ddmm()
    entries = await _force_load_if_empty(label, group, bot)
    text = formatting.format_what_now(label, group, entries, now=now())
    await _send(message, text, menu=True)


@router.message(F.text == BTN_SCHEDULE)
async def btn_schedule(message: Message) -> None:
    await message.answer(SCHEDULE_INFO_TEXT, reply_markup=build_main_menu())


# --- change_group, подписка ------------------------------------------------


@router.message(Command("week"))
async def cmd_week(message: Message) -> None:
    group = await _require_group(message)
    if not group:
        return
    sent = 0
    for _day_name, label in week_days():
        entries = await _load(label, group)
        if not entries:
            continue
        text = formatting.format_schedule(
            label, group, entries, now=now(), with_state=False, empty_text="Пар нет 🎉"
        )
        await _send(message, text)
        sent += 1
    if sent == 0:
        await message.answer("Расписание на неделю пока не загружено.")


@router.message(Command("change_group"))
async def cmd_change_group(message: Message) -> None:
    async with SessionLocal() as session:
        groups = await crud.get_groups(session)
    if not groups:
        await message.answer("Расписание ещё не загружено, групп пока нет. Попробуй позже.")
        return
    await message.answer("Выбери группу:", reply_markup=build_groups_keyboard(groups))


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    async with SessionLocal() as session:
        await crud.set_subscribed(session, message.from_user.id, True)
        await session.commit()
    await message.answer(
        "🔔 Готово! Теперь я буду присылать уведомление, когда появится новое расписание."
    )


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message) -> None:
    async with SessionLocal() as session:
        await crud.set_subscribed(session, message.from_user.id, False)
        await session.commit()
    await message.answer(
        "🔕 Уведомления о расписании выключены. "
        "Расписание можно посмотреть кнопками «Сегодня» и «Завтра»."
    )
