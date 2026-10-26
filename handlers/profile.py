"""Профиль пользователя, избранные группы и поддержка."""
import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from db import SessionLocal
from db import crud
from keyboards.groups import build_groups_keyboard
from keyboards.profile import (
    build_favorites_keyboard,
    build_profile_keyboard,
    build_slot_keyboard,
)
from services import formatting

router = Router()

SUPPORT_TEXT = (
    "🛠 <b>Поддержка</b>\n\n"
    "🔹 Возникли вопросы?\n"
    "🔹 Есть предложения?\n\n"
    "Напишите в личные сообщения разработчику — @x6anax6\n\n"
    "Created with ❤️ love by @x6anax6"
)

SCHEDULE_INFO_TEXT = (
    "📖 <b>Расписание</b>\n\n"
    "Жми кнопки внизу:\n"
    "📅 <b>Сегодня</b> — пары на сегодня\n"
    "📅 <b>Завтра</b> — пары на завтра\n"
    "🔔 <b>Что сейчас</b> — идёт ли пара прямо сейчас\n\n"
    "Сменить группу можно в разделе 👤 <b>Профиль</b>."
)


def _esc(value) -> str:
    return html.escape(str(value or ""), quote=False)


async def _profile_text(telegram_id: int, username: str | None) -> str:
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, telegram_id)
        group = user.group
        subscribed = user.subscribed
        await session.commit()
    return formatting.format_profile(username, group, subscribed)


async def _favorites_text(telegram_id: int) -> str:
    async with SessionLocal() as session:
        favorites = await crud.get_favorites(session, telegram_id)
    return formatting.format_favorites(favorites)


# --- кнопки главного меню --------------------------------------------------


@router.message(F.text == "👤 Профиль")
async def btn_profile(message: Message) -> None:
    text = await _profile_text(message.from_user.id, message.from_user.username)
    await message.answer(text, reply_markup=build_profile_keyboard())


@router.message(F.text == "🛠 Поддержка")
async def btn_support(message: Message) -> None:
    await message.answer(SUPPORT_TEXT)


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    text = await _profile_text(message.from_user.id, message.from_user.username)
    await message.answer(text, reply_markup=build_profile_keyboard())


@router.message(Command("support"))
async def cmd_support(message: Message) -> None:
    await message.answer(SUPPORT_TEXT)


# --- профиль: inline-кнопки ------------------------------------------------


@router.callback_query(F.data == "prof:group")
async def cb_profile_group(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        groups = await crud.get_groups(session)
    await callback.answer()
    if not groups:
        await callback.message.answer("Расписание ещё не загружено, групп пока нет.")
        return
    await callback.message.answer("Выбери группу:", reply_markup=build_groups_keyboard(groups))


@router.callback_query(F.data == "prof:back")
async def cb_profile_back(callback: CallbackQuery) -> None:
    text = await _profile_text(callback.from_user.id, callback.from_user.username)
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=build_profile_keyboard())
    except Exception:
        await callback.message.answer(text, reply_markup=build_profile_keyboard())


# --- избранные --------------------------------------------------------------


@router.callback_query(F.data == "fav:list")
async def cb_fav_list(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        favorites = await crud.get_favorites(session, callback.from_user.id)
    text = await _favorites_text(callback.from_user.id)
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=build_favorites_keyboard(favorites))
    except Exception:
        await callback.message.answer(text, reply_markup=build_favorites_keyboard(favorites))


@router.callback_query(F.data.startswith("fav:slot:"))
async def cb_fav_slot(callback: CallbackQuery) -> None:
    slot = int(callback.data.split(":")[2])

    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, callback.from_user.id)
        current_group = user.group
        favorites = await crud.get_favorites(session, callback.from_user.id)
        slot_group = favorites.get(slot)

        if slot_group:
            await callback.answer()
            await callback.message.answer(
                f"⭐ Слот {slot}: <b>{_esc(slot_group)}</b>\n\nЧто сделать?",
                reply_markup=build_slot_keyboard(slot, slot_group),
            )
            return

        if not current_group:
            await callback.answer()
            await callback.message.answer(
                "Сначала выбери группу: /start или 👤 Профиль → «Сменить группу»."
            )
            return

        await crud.set_favorite(session, callback.from_user.id, slot, current_group)
        await session.commit()
        favorites = await crud.get_favorites(session, callback.from_user.id)

    text = await _favorites_text(callback.from_user.id)
    await callback.answer(f"Группа {current_group} сохранена в слот {slot}")
    try:
        await callback.message.edit_text(text, reply_markup=build_favorites_keyboard(favorites))
    except Exception:
        await callback.message.answer(text, reply_markup=build_favorites_keyboard(favorites))


@router.callback_query(F.data.startswith("fav:usegroup:"))
async def cb_fav_use(callback: CallbackQuery) -> None:
    slot = int(callback.data.split(":")[2])

    async with SessionLocal() as session:
        favorites = await crud.get_favorites(session, callback.from_user.id)
        group = favorites.get(slot)
        if not group:
            await callback.answer("Слот пуст", show_alert=True)
            return
        await crud.set_group(session, callback.from_user.id, group)
        await session.commit()

    await callback.answer(f"Текущая группа: {group}")
    await callback.message.answer(f"✅ Текущая группа: <b>{_esc(group)}</b>")


@router.callback_query(F.data.startswith("fav:clear:"))
async def cb_fav_clear(callback: CallbackQuery) -> None:
    slot = int(callback.data.split(":")[2])

    async with SessionLocal() as session:
        await crud.clear_favorite(session, callback.from_user.id, slot)
        await session.commit()
        favorites = await crud.get_favorites(session, callback.from_user.id)

    text = await _favorites_text(callback.from_user.id)
    await callback.answer(f"Слот {slot} очищен")
    try:
        await callback.message.edit_text(text, reply_markup=build_favorites_keyboard(favorites))
    except Exception:
        await callback.message.answer(text, reply_markup=build_favorites_keyboard(favorites))
