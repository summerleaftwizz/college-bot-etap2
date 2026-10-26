"""Админ-панель: доступна только пользователю с ID из settings.ADMIN_ID."""
import asyncio
import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import settings
from db import SessionLocal
from db import crud
from keyboards.admin import build_admin_keyboard
from services import watcher

logger = logging.getLogger(__name__)
router = Router()


class AdminStates(StatesGroup):
    broadcast_text = State()


def _is_admin(user_id: int) -> bool:
    return settings.ADMIN_ID != 0 and user_id == settings.ADMIN_ID


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return
    await message.answer("<b>🛠 Админ-панель</b>", reply_markup=build_admin_keyboard())


@router.callback_query(F.data == "adm:broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast_text)
    await callback.answer()
    await callback.message.answer("Отправь текст рассылки одним сообщением:")


@router.message(AdminStates.broadcast_text)
async def on_broadcast_text(message: Message, state: FSMContext, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    text = (message.text or "").strip()
    await state.clear()
    if not text:
        await message.answer("Пустой текст — рассылка отменена.")
        return

    async with SessionLocal() as session:
        users = await crud.list_all_users(session)

    sent, failed = 0, 0
    delay = settings.BROADCAST_DELAY_MS / 1000
    for user in users:
        try:
            await bot.send_message(user.telegram_id, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(delay)
    await message.answer(f"📢 Рассылка завершена: отправлено {sent}, ошибок {failed}.")


@router.callback_query(F.data == "adm:groupmembers")
async def cb_group_members(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with SessionLocal() as session:
        admin = await crud.get_user(session, callback.from_user.id)
        group = admin.group if admin else None
        members = await crud.list_users_in_group(session, group) if group else []

    await callback.answer()
    if not group:
        await callback.message.answer("У тебя не выбрана группа.")
        return
    if not members:
        await callback.message.answer(f"В группе <b>{html.escape(group)}</b> пока никого нет.")
        return

    lines = [f"👥 <b>Группа {html.escape(group)}</b> ({len(members)}):"]
    for m in members:
        uname = f"@{html.escape(m.username)}" if m.username else "—"
        lines.append(f"• {uname} — <code>{m.telegram_id}</code>")
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "adm:stats")
async def cb_stats(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    async with SessionLocal() as session:
        total = await crud.count_users(session)
        stats = await crud.group_stats(session)

    await callback.answer()
    lines = [f"📊 <b>Статистика групп</b>\n\nВсего пользователей: <b>{total}</b>\n"]
    for group, count in stats:
        name = html.escape(group) if group else "без группы"
        lines.append(f"• {name}: {count}")
    await callback.message.answer("\n".join(lines))


# --- старые админ-команды --------------------------------------------------


@router.message(Command("admin_known"))
async def cmd_admin_known(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return

    async with SessionLocal() as session:
        known = await crud.list_known(session)

    if not known:
        await message.answer("Известных дат пока нет.")
        return

    lines = []
    for k in known:
        dt = k.notified_at.strftime("%Y-%m-%d %H:%M:%S %Z") if k.notified_at else "—"
        lines.append(f"• {k.date_folder} — {dt}")
    await message.answer("Известные даты:\n" + "\n".join(lines))


@router.message(Command("admin_reparse"))
async def cmd_admin_reparse(message: Message, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return

    await message.answer("Перепарсиваю последнюю дату и рассылаю…")
    result = await watcher.reparse_latest(bot)
    if result:
        await message.answer(f"Готово: дата {result} перепарсена и разослана.")
    else:
        await message.answer("Не удалось перепарсить (см. логи).")
