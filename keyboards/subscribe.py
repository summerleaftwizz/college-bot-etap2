"""Клавиатура обязательной подписки на канал."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import CHANNEL_LINK


def build_subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Подписаться", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="✔️ Проверить подписку", callback_data="sub:check")],
        ]
    )