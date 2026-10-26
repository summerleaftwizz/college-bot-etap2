from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from db import SessionLocal
from db import crud
from keyboards.groups import build_groups_keyboard
from keyboards.menu import build_main_menu

router = Router()

WELCOME_TEXT = (
    "Привет! Твоя группа: <b>{group}</b>\n\n"
    "Кнопки внизу покажут расписание на сегодня и завтра, а «Что сейчас» — "
    "какая пара идёт прямо сейчас.\n\n"
    "Команды:\n"
    "/today — расписание на сегодня\n"
    "/tomorrow — на завтра\n"
    "/subscribe, /unsubscribe — уведомления о расписании"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user.id)
        group = user.group
        await session.commit()

    if group:
        await message.answer(WELCOME_TEXT.format(group=group), reply_markup=build_main_menu())
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
        await session.commit()

    await callback.answer("Группа сохранена")
    if callback.message:
        await callback.message.edit_text(
            f"Группа: <b>{group}</b> ✅\n\nВыбери, что показать:", reply_markup=build_main_menu()
        )


@router.callback_query(F.data == "menu:group")
async def cb_menu_group(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        groups = await crud.get_groups(session)
    if not groups:
        await callback.answer("Расписание ещё не загружено.", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.answer("Выбери группу:", reply_markup=build_groups_keyboard(groups))
