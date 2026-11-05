"""Кнопка «👨‍🏫 Преподаватели»: поиск расписания преподавателя по фамилии.

Пользователь вводит фамилию, бот ищет все пары преподавателя на текущую
неделю (Пн–Сб) в БД schedule_entries и выводит списком:
день, время, группа, аудитория. Основная группа пользователя не меняется.
"""
import html
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from db import SessionLocal
from db import crud
from handlers import menu_dispatch
from keyboards.menu import BTN_TEACHERS, build_main_menu
from services import watcher
from services.formatting import split_message
from utils import WEEKDAY_NAMES, week_days

logger = logging.getLogger(__name__)
router = Router()

SEARCH_PROMPT = "Введите фамилию преподавателя для поиска расписания:"


class TeacherSearchStates(StatesGroup):
    waiting_name = State()


@router.message(F.text == BTN_TEACHERS)
async def btn_teachers(message: Message, state: FSMContext) -> None:
    await state.set_state(TeacherSearchStates.waiting_name)
    await message.answer(
        SEARCH_PROMPT,
        reply_markup=build_main_menu(),
    )


@router.message(TeacherSearchStates.waiting_name)
async def on_teacher_name(message: Message, state: FSMContext) -> None:
    if await menu_dispatch.cancel_fsm_on_menu(message, state):
        return

    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(
            "Фамилия слишком короткая. Введите ещё раз:",
            reply_markup=build_main_menu(),
        )
        return

    await state.clear()

    # Собираем пары преподавателя за Пн–Сб текущей недели.
    found: list[tuple[str, str, list]] = []
    for day_name, label in week_days():
        async with SessionLocal() as session:
            entries = await crud.get_teacher_schedule(session, label, name)
        if entries:
            found.append((day_name, label, entries))

    if not found:
        # Возможно, расписание ещё не скачано — пробуем принудительно.
        try:
            await watcher.run_check(message.bot)
        except Exception:
            logger.exception("ошибка принудительной загрузки расписания")
        for day_name, label in week_days():
            async with SessionLocal() as session:
                entries = await crud.get_teacher_schedule(session, label, name)
            if entries:
                found.append((day_name, label, entries))

    esc = html.escape(name, quote=False)
    if not found:
        await message.answer(
            f"❌ Преподаватель <b>{esc}</b> не найден в расписании на текущую неделю.\n\n"
            "Попробуйте ещё раз — /teachers",
            reply_markup=build_main_menu(),
        )
        return

    lines = [f"👨‍🏫 <b>{esc}</b> — расписание на неделю:\n"]
    for day_name, label, entries in found:
        lines.append(f"<b>{day_name} ({label})</b>")
        for e in sorted(entries, key=lambda x: (x.lesson_number, x.group)):
            time = (e.time or "").strip()
            if not time:
                time = f"{e.lesson_number} пара"
            subject = html.escape(e.subject or "", quote=False)
            room = html.escape(e.room or "—", quote=False)
            group = html.escape(e.group or "", quote=False)
            lines.append(f"  • {time} — {group} — {subject} (каб. {room})")
        lines.append("")
    text = "\n".join(lines).rstrip()

    for chunk in split_message(text):
        await message.answer(chunk, reply_markup=build_main_menu())
