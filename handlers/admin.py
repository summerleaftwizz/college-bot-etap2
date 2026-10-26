from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from config import settings
from db import SessionLocal
from db import crud
from services import watcher

router = Router()


def _is_admin(user_id: int) -> bool:
    return settings.ADMIN_ID != 0 and user_id == settings.ADMIN_ID


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
