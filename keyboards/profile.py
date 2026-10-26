"""Клавиатуры профиля и избранного."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.crud import FAVORITE_SLOTS


def build_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Сменить группу", callback_data="prof:group")],
            [InlineKeyboardButton(text="⭐ Избранные", callback_data="fav:list")],
        ]
    )


def build_favorites_keyboard(favorites: dict[int, str | None]) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text=f"⭐ {slot}", callback_data=f"fav:slot:{slot}"
        )
        for slot in FAVORITE_SLOTS
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text="⬅️ Назад в профиль", callback_data="prof:back")],
        ]
    )


def build_slot_keyboard(slot: int, group: str) -> InlineKeyboardMarkup:
    """Клавиатура для занятого слота: сделать текущей / очистить."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сделать текущей", callback_data=f"fav:usegroup:{slot}"
                )
            ],
            [InlineKeyboardButton(text="🗑 Очистить слот", callback_data=f"fav:clear:{slot}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="fav:list")],
        ]
    )
