"""Главное меню бота: постоянная (закреплённая) Reply-клавиатура.

Раскладка:
  [📖 Расписание]
  [📅 Сегодня] [📅 Завтра]
  [🔔 Что сейчас]
  [👤 Профиль] [🛠 Поддержка]

Кнопки реагируют на ТЕКСТ сообщения, обработчики вешаются на F.text == BTN_*.
"""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_SCHEDULE = "📖 Расписание"
BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "📅 Завтра"
BTN_NOW = "🔔 Что сейчас"
BTN_PROFILE = "👤 Профиль"
BTN_SUPPORT = "🛠 Поддержка"

MENU_BUTTONS = (BTN_SCHEDULE, BTN_TODAY, BTN_TOMORROW, BTN_NOW, BTN_PROFILE, BTN_SUPPORT)


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SCHEDULE)],
            [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_TOMORROW)],
            [KeyboardButton(text=BTN_NOW)],
            [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_SUPPORT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери действие…",
    )
