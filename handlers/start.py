from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from db import SessionLocal
from db import crud
from keyboards.groups import build_groups_keyboard
from keyboards.menu import build_main_menu

router = Router()

WELCOME_TEXT = (
    "👋 Привет! Я бот для просмотра расписания.\n\n"
    "📅 Здесь ты можешь узнать, какие пары сегодня и завтра.\n"
    "👤 В профиле можно сменить группу, добавить долги и настроить уведомления.\n"
    "💡 Если что-то не работает — пиши в поддержку!\n\n"
    "Выбирай действие на клавиатуре ниже 👇"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(
            session, message.from_user.id, username=message.from_user.username
        )
        group = user.group
        await session.commit()

    if group:
        await message.answer(WELCOME_TEXT, reply_markup=build_main_menu())
        return

    async with SessionLocal() as session:
        groups = await crud.get_groups(session)

    if not groups:
        await message.answer(
            "Привет! Подожди, расписание ещё не загружено. "
            "Как только появится первый файл — сможешь выбрать группу."
        )
    else:
        await message.answer("Привет! Выбери свою группу:", reply_markup=build_groups_keyboard(groups))


@router.callback_query(F.data.startswith("g:"))
async def on_group_selected(callback: CallbackQuery) -> None:
    group = callback.data[len("g:"):]
    async with SessionLocal() as session:
        await crud.set_group(session, callback.from_user.id, group)
        user = await crud.get_user(session, callback.from_user.id)
        if user is not None and callback.from_user.username:
            user.username = callback.from_user.username
        await session.commit()

    await callback.answer("Группа сохранена")
    if callback.message:
        await callback.message.edit_text(
            f"Группа: <b>{group}</b> ✅",
            reply_markup=None,
        )
        await callback.message.answer(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=build_main_menu(),
        )