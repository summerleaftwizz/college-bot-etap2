"""Трекинг ID сообщений бота для «Очистить чат» и автоудаления.

Бот не может запросить историю чата через Bot API, поэтому мы сами
запоминаем ID своих сообщений (в памяти, по чатам) и удаляем их по запросу.
"""
import asyncio
from collections import defaultdict, deque

from db import SessionLocal
from db import crud

_sent: dict[int, deque[int]] = defaultdict(lambda: deque(maxlen=200))
_lock = asyncio.Lock()


async def track(chat_id: int, message) -> None:
    """Запоминает ID сообщения, отправленного ботом в чат."""
    if message is None:
        return
    async with _lock:
        _sent[chat_id].append(int(message.message_id))


async def tracked(chat_id: int, limit: int = 20) -> list[int]:
    """Последние `limit` ID сообщений бота в чате (старые к новым)."""
    async with _lock:
        ids = list(_sent.get(chat_id, ()))
    return ids[-limit:]


async def forget(chat_id: int, message_ids: list[int]) -> None:
    """Забывает сообщения, которые уже удалены (чтобы не пытаться снова)."""
    if not message_ids:
        return
    async with _lock:
        d = _sent.get(chat_id)
        if d is None:
            return
        removed = set(message_ids)
        _sent[chat_id] = deque(
            (mid for mid in d if mid not in removed), maxlen=d.maxlen
        )


async def clear_chat(bot, chat_id: int, limit: int = 20) -> tuple[int, int]:
    """Удаляет последние `limit` сообщений бота. Возвращает (успешно, не удалось)."""
    ids = await tracked(chat_id, limit)
    ok, fail = 0, 0
    for mid in ids:
        try:
            await bot.delete_message(chat_id, mid)
            ok += 1
        except Exception:
            fail += 1
    if ids:
        await forget(chat_id, ids)
    return ok, fail


async def auto_clean(chat_id: int, telegram_id: int, bot) -> None:
    """Если у пользователя включено автоудаление — удаляет предыдущие
    сообщения бота в этом чате перед новым ответом."""
    async with SessionLocal() as session:
        auto = await crud.get_auto_delete(session, telegram_id)
    if not auto:
        return
    ids = await tracked(chat_id, 50)
    for mid in ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass
    if ids:
        await forget(chat_id, ids)
