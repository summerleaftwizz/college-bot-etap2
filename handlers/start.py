from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from db import SessionLocal
from db import crud
from keyboards.groups import build_groups_keyboard

router = Router()

WELCOME_TEXT = (
    "Привет! Твоя группа: <b>{group}</b>\n\n"
    "Команды:\n"
    "/today — расписание на сегодня\n"
    "/tomorrow — на завтра\n"
    "/change_group — сменить группу\n"
    "/subscribe, /unsubscribe — уведомления о расписании"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with SessionLocal() as session:
        user = await crud.get_or_create_user(session, message.from_user.id)
        group = user.group
        await session.commit()

    if group:
        await message.answer(WELCOME_TEXT.format(group=group))
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
            f"Группа: <b>{group}</b> ✅\n\nТеперь /today и /tomorrow покажут твоё расписание."
        )
