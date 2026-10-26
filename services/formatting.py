"""Форматирование расписания в HTML-текст для Telegram."""
import html
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from config import bells_for_weekday, settings
from utils import WEEKDAY_NAMES, now as _now

EMOJI_NUMS = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
    10: "🔟",
}

SEPARATOR = "━━━━━━━━━━━━━━"


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def _emoji_num(n: int) -> str:
    return EMOJI_NUMS.get(n, f"{n}.")


def _to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _weekday_of(date_label: str, ref: datetime) -> int:
    """День недели по метке 'DD.MM'; год берём из ref (функция остаётся чистой)."""
    try:
        parts = date_label.split(".")
        d, m = int(parts[0]), int(parts[1])
    except Exception:
        return ref.weekday()
    year = ref.year
    try:
        dt = date(year, m, d)
    except ValueError:
        return ref.weekday()
    if dt < ref.date() - timedelta(days=180):
        try:
            dt = date(year + 1, m, d)
        except ValueError:
            pass
    return dt.weekday()


@dataclass
class State:
    """Состояние расписания на момент времени."""

    kind: str  # ongoing | break | window | before | after | empty
    current: Optional[object] = None      # идущая сейчас пара
    next_lesson: Optional[object] = None  # ближайшая следующая непустая пара
    until: Optional[str] = None           # HH:MM — до какого времени
    minutes_left: Optional[int] = None    # минут до until


def _next_active(active, lesson_number: int):
    for l in active:
        if l.lesson_number > lesson_number:
            return l
    return None


def get_current_state(entries, now: datetime) -> State:
    """Чистая функция: состояние расписания на момент now.

    Сетка звонков выбирается по дню недели ДАТЫ РАСПИСАНИЯ (entries[0].date),
    а не по now — поэтому /tomorrow, запрошенный в пятницу, получит
    субботнюю сетку.
    """
    if not entries:
        return State(kind="empty")

    date_label = getattr(entries[0], "date", None)
    weekday = _weekday_of(date_label, now) if date_label else now.weekday()
    bells = bells_for_weekday(weekday)
    if not bells:  # воскресенье — занятий нет
        return State(kind="empty")

    active = sorted(
        [e for e in entries if (getattr(e, "subject", "") or "").strip()],
        key=lambda e: e.lesson_number,
    )
    if not active:
        return State(kind="empty")

    now_min = now.hour * 60 + now.minute

    # идёт пара
    for lesson in active:
        b = bells.get(lesson.lesson_number)
        if not b:
            continue
        start, end = b
        if _to_min(start) <= now_min < _to_min(end):
            return State(
                kind="ongoing",
                current=lesson,
                next_lesson=_next_active(active, lesson.lesson_number),
                until=end,
                minutes_left=_to_min(end) - now_min,
            )

    # до начала / после конца / между парами
    prev_lesson = None
    next_lesson = None
    for lesson in active:
        b = bells.get(lesson.lesson_number)
        if not b:
            continue
        start, end = b
        if _to_min(end) <= now_min:
            prev_lesson = lesson
        elif _to_min(start) > now_min and next_lesson is None:
            next_lesson = lesson

    if prev_lesson is None and next_lesson is None:
        return State(kind="empty")
    if next_lesson is None:
        return State(kind="after", current=prev_lesson)
    if prev_lesson is None:
        start = bells[next_lesson.lesson_number][0]
        return State(
            kind="before",
            next_lesson=next_lesson,
            until=start,
            minutes_left=_to_min(start) - now_min,
        )

    start = bells[next_lesson.lesson_number][0]
    is_break = next_lesson.lesson_number == prev_lesson.lesson_number + 1
    return State(
        kind="break" if is_break else "window",
        current=prev_lesson,
        next_lesson=next_lesson,
        until=start,
        minutes_left=_to_min(start) - now_min,
    )


def _state_block(state: State, bells) -> list[str]:
    """Строки шапки «сейчас/следующая» для /today."""
    if state.kind == "ongoing":
        lines = [f"⏱️ <i>Сейчас: {state.current.lesson_number} пара, до {esc(state.until)}</i>"]
        if state.next_lesson:
            nxt = state.next_lesson
            start = bells.get(nxt.lesson_number, ("", ""))[0]
            lines.append(f"➡️ <i>Следующая: {nxt.lesson_number} пара в {esc(start)}</i>")
        return lines
    if state.kind in ("break", "window"):
        word = "Перемена" if state.kind == "break" else "Окно"
        lines = [f"⏱️ <i>{word} до {esc(state.until)}</i>"]
        if state.next_lesson:
            nxt = state.next_lesson
            room = f", каб. {esc(nxt.room)}" if nxt.room else ""
            lines.append(f"➡️ <i>Дальше: {nxt.lesson_number} пара — {esc(nxt.subject)}{room}</i>")
        return lines
    if state.kind == "before":
        nxt = state.next_lesson
        start = bells.get(nxt.lesson_number, ("", ""))[0]
        room = f" (каб. {esc(nxt.room)})" if nxt.room else ""
        return [f"➡️ <i>Следующая: {nxt.lesson_number} пара в {esc(start)} — {esc(nxt.subject)}{room}</i>"]
    if state.kind == "after":
        return ["⏱️ <i>Пары на сегодня закончились</i>"]
    return []


def _room_text(room) -> str:
    """Текст аудитории: 'max' -> «пара в максе», иначе «каб. X»."""
    r = (room or "").strip()
    if not r:
        return ""
    if r.lower() == "max":
        return "пара в максе"
    return f"каб. {esc(r)}"


def _render_lessons(entries, bells, empty_text: str) -> str:
    by_num = {e.lesson_number: e for e in entries}
    nums = sorted(by_num)
    active_nums = [n for n in nums if (by_num[n].subject or "").strip()]
    if not active_nums:
        return f"<i>{esc(empty_text)}</i>"

    # показываем от первой записи в расписании до последней непустой пары
    first, last = nums[0], active_nums[-1]
    blocks: list[str] = []

    for n in range(first, last + 1):
        entry = by_num.get(n)
        if entry is None or not (entry.subject or "").strip():
            blocks.append(f"{_emoji_num(n)} <i>пара — окно</i>")
            continue
        b = bells.get(n)
        time_part = ""
        if settings.SHOW_TIME and b:
            time_part = f" <b>{esc(b[0])} – {esc(b[1])}</b>"
        lines = [f"{_emoji_num(n)}{time_part}"]
        lines.append(f"📚 {esc(entry.subject)}")
        below: list[str] = []
        room_text = _room_text(entry.room)
        if room_text:
            below.append(f"🚪 {room_text}")
        teacher = getattr(entry, "teacher", None)
        if teacher:
            below.append(f"👤 {esc(teacher)}")
        if below:
            lines.append("—————")
            lines.extend(below)
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _header(date_label: str, group: str, ref: datetime) -> list[str]:
    weekday = _weekday_of(date_label, ref)
    return [
        f"📅 <b>Расписание на {esc(date_label)} ({esc(WEEKDAY_NAMES[weekday].lower())})</b>",
        f"👥 <b>{esc(group)}</b>",
    ]


def format_schedule(
    date_label: str,
    group: str,
    entries,
    *,
    now: Optional[datetime] = None,
    with_state: bool = False,
    empty_text: str = "Пар нет 🎉",
) -> str:
    ref = now or _now()
    weekday = _weekday_of(date_label, ref)
    bells = bells_for_weekday(weekday)

    lines = _header(date_label, group, ref)
    if with_state and entries:
        state = get_current_state(entries, ref)
        state_lines = _state_block(state, bells)
        if state_lines:
            lines.append("")
            lines.extend(state_lines)
    lines.append("")
    lines.append(SEPARATOR)
    lines.append("")
    lines.append(_render_lessons(entries, bells, empty_text))
    return "\n".join(lines)


def format_notification(
    date_label: str, group: str, entries, *, now: Optional[datetime] = None
) -> str:
    """Уведомление о новом расписании: без шапки «сейчас», вместо неё —
    «Начало занятий в HH:MM, всего N пар»."""
    ref = now or _now()
    weekday = _weekday_of(date_label, ref)
    bells = bells_for_weekday(weekday)
    active = sorted(
        [e for e in entries if (e.subject or "").strip()],
        key=lambda e: e.lesson_number,
    )

    lines = [f"🔔 <b>Появилось новое расписание на {esc(date_label)}!</b>", ""]
    lines.extend(_header(date_label, group, ref))
    if active:
        b = bells.get(active[0].lesson_number)
        start = b[0] if b else "—"
        lines.append("")
        lines.append(f"🔔 <i>Начало занятий в {esc(start)}, всего {len(active)} пар</i>")
    lines.append("")
    lines.append(SEPARATOR)
    lines.append("")
    lines.append(_render_lessons(entries, bells, "Пар нет 🎉"))
    return "\n".join(lines)


def format_what_now(
    date_label: str, group: str, entries, *, now: Optional[datetime] = None
) -> str:
    """Короткий ответ на «Что сейчас»: состояние дня в 1–2 строки.

    minutes_left считаем только когда известны минуты (state.until = HH:MM).
    """
    ref = now or _now()
    weekday = _weekday_of(date_label, ref)
    bells = bells_for_weekday(weekday)
    state = get_current_state(entries, ref)

    def _room(lesson) -> str:
        t = _room_text(getattr(lesson, "room", ""))
        return f", {t}" if t else ""

    if state.kind == "empty":
        return "💤 На этот день пар нет."

    if state.kind == "ongoing":
        c = state.current
        return (
            f"⏱️ <b>Сейчас:</b> {c.lesson_number} пара — {esc(c.subject)}{_room(c)}\n"
            f"⏳ До конца {state.minutes_left} мин (до {esc(state.until)})"
        )

    if state.kind in ("break", "window"):
        nxt = state.next_lesson
        word = "Перемена" if state.kind == "break" else "Окно"
        return (
            f"☕ <b>{word}</b> — ещё {state.minutes_left} мин (до {esc(state.until)})\n"
            f"➡️ Дальше: {nxt.lesson_number} пара — {esc(nxt.subject)}{_room(nxt)}"
        )

    if state.kind == "before":
        nxt = state.next_lesson
        start = bells.get(nxt.lesson_number, ("—", ""))[0]
        return (
            f"🌅 Занятия начнутся в {esc(state.until)} (через {state.minutes_left} мин)\n"
            f"➡️ Первая: {nxt.lesson_number} пара — {esc(nxt.subject)}{_room(nxt)}"
        )

    # after
    c = state.current
    return f"✅ Пары на сегодня закончились (последняя — {c.lesson_number}, {esc(c.subject)})"


def format_profile(username: Optional[str], group: Optional[str], subscribed: bool) -> str:
    """Карточка профиля пользователя."""
    uname = f"@{esc(username)}" if username else "—"
    status = "включены 🔔" if subscribed else "выключены 🔕"
    return (
        "👤 <b>Профиль</b>\n\n"
        f"🆔 {uname}\n"
        "🎓 Роль: Студент\n"
        f"👥 Уч. группа: <b>{esc(group) if group else '—'}</b>\n"
        f"🔔 Уведомления: {status}"
    )


def format_favorites(favorites: dict) -> str:
    """Список избранных групп: слоты 1..3, пустой слот — «отсутствует»."""
    lines = ["❤️ Это — ваши избранные группы:", ""]
    for slot in (1, 2, 3):
        group = favorites.get(slot)
        lines.append(f"{slot}. {esc(group) if group else 'отсутствует'}")
    return "\n".join(lines)


def split_message(text: str, limit: int = 4096) -> list[str]:
    """Разбивает длинный HTML-текст на части по пустым строкам (не обрезая)."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) > limit and current:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
