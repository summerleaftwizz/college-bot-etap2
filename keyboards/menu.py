"""Главное меню бота: inline-кнопки «Сегодня», «Завтра», «Что сейчас»."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="menu:today"),
                InlineKeyboardButton(text="📅 Завтра", callback_data="menu:tomorrow"),
            ],
            [InlineKeyboardButton(text="🔔 Что сейчас", callback_data="menu:now")],
            [InlineKeyboardButton(text="👥 Сменить группу", callback_data="menu:group")],
        ]
    )
