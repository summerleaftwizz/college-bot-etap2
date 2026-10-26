from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_groups_keyboard(groups: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура выбора группы. Callback data: 'g:<группа>'."""
    rows = [[InlineKeyboardButton(text=g, callback_data=f"g:{g}")] for g in groups]
    return InlineKeyboardMarkup(inline_keyboard=rows)
