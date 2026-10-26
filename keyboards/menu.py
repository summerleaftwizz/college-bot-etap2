"""Главное меню бота: постоянная (закреплённая) Reply-клавиатура.

Кнопки реагируют на ТЕКСТ сообщения, поэтому обработчики вешаются на
F.text == BTN_*.
"""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "📅 Завтра"
BTN_NOW = "🔔 Что сейчас"
BTN_GROUP = "👥 Сменить группу"


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_TOMORROW)],
            [KeyboardButton(text=BTN_NOW), KeyboardButton(text=BTN_GROUP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери действие…",
    )
