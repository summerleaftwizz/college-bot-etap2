"""Проверка обязательной подписки на канал (Force Subscribe)."""
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from config import CHANNEL_ID

logger = logging.getLogger(__name__)

# Статусы участника, при которых считаем, что пользователь подписан.
SUBSCRIBED_STATUSES = {"creator", "administrator", "member"}


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Подписан ли пользователь на канал.

    Если проверка невозможна из-за настроек канала (бот не админ, канал не
    найден), не блокируем пользователя — пишем предупреждение в лог.
    """
    if not CHANNEL_ID:
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
    except TelegramBadRequest as exc:
        text = str(exc).lower()
        # «user not found» / «participant_id_invalid» — пользователя в канале нет
        if "user not found" in text or "participant" in text or "member" in text:
            return False
        logger.warning("не удалось проверить подписку (%s): %s", user_id, exc)
        return True
    except TelegramAPIError as exc:
        logger.warning("ошибка Telegram при проверке подписки (%s): %s", user_id, exc)
        return True

    status = getattr(member, "status", "")
    status = getattr(status, "value", status)
    return str(status) in SUBSCRIBED_STATUSES