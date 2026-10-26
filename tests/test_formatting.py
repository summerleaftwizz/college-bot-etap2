"""Тесты Этапа 2: сетки звонков, get_current_state, форматирование."""
from datetime import datetime
from types import SimpleNamespace

from config import BELLS_SATURDAY, BELLS_WEEKDAY, bells_for_weekday
from services.formatting import (
    get_current_state,
    format_notification,
    format_schedule,
    format_what_now,
    split_message,
)


def entry(num, subject="Предмет", room="", teacher="", date="26.10"):
    return SimpleNamespace(
        lesson_number=num, subject=subject, room=room, teacher=teacher, date=date
    )


# --- выбор сетки звонков ---------------------------------------------------

def test_bells_for_weekday():
    assert bells_for_weekday(0) is BELLS_WEEKDAY          # понедельник
    assert bells_for_weekday(4) is BELLS_WEEKDAY          # пятница
    assert bells_for_weekday(5) is BELLS_SATURDAY         # суббота
    assert bells_for_weekday(6) == {}                     # воскресенье


def test_saturday_grid_differs_from_weekday():
    assert BELLS_SATURDAY[2] == ("10:10", "11:40")
    assert BELLS_WEEKDAY[2] == ("10:20", "11:50")


def test_tomorrow_from_friday_uses_saturday_grid():
    # 23.10.2026 — пятница, 24.10.2026 — суббота (сетка субботы: 2 пара в 10:10)
    now = datetime(2026, 10, 23, 12, 0)
    text = format_schedule("24.10", "ГР-1", [entry(2, date="24.10")], now=now)
    assert "10:10 – 11:40" in text
    assert "10:20" not in text


# --- get_current_state ------------------------------------------------------

def test_state_ongoing():
    now = datetime(2026, 10, 26, 9, 0)  # понедельник, внутри 1 пары
    state = get_current_state([entry(1), entry(2)], now)
    assert state.kind == "ongoing"
    assert state.current.lesson_number == 1
    assert state.until == "10:00"
    assert state.next_lesson.lesson_number == 2


def test_state_break():
    now = datetime(2026, 10, 26, 10, 5)  # между 1 и 2 парами
    state = get_current_state([entry(1), entry(2)], now)
    assert state.kind == "break"
    assert state.until == "10:20"


def test_state_window():
    now = datetime(2026, 10, 26, 11, 0)  # слот 2 пары пуст, 3-я заполнена
    state = get_current_state([entry(1), entry(2, subject=""), entry(3)], now)
    assert state.kind == "window"
    assert state.next_lesson.lesson_number == 3


def test_state_before():
    now = datetime(2026, 10, 26, 7, 30)
    state = get_current_state([entry(1), entry(2)], now)
    assert state.kind == "before"
    assert state.next_lesson.lesson_number == 1


def test_state_after():
    now = datetime(2026, 10, 26, 20, 0)
    state = get_current_state([entry(1), entry(2)], now)
    assert state.kind == "after"


def test_state_empty():
    now = datetime(2026, 10, 26, 12, 0)
    assert get_current_state([], now).kind == "empty"
    assert get_current_state([entry(1, subject="")], now).kind == "empty"


# --- форматирование ---------------------------------------------------------

def test_format_html_escaping():
    text = format_schedule("26.10", "ГР<1>", [entry(1, subject="Мат<ем>атика", room="&304")],
                           now=datetime(2026, 10, 26, 12, 0))
    assert "Мат&lt;ем&gt;атика" in text
    assert "каб. &amp;304" in text
    assert "ГР&lt;1&gt;" in text
    assert "<em>" not in text


def test_format_no_teacher_line_when_empty():
    text = format_schedule("26.10", "ГР-1", [entry(1, teacher="")],
                           now=datetime(2026, 10, 26, 12, 0))
    assert "👤" not in text
    text = format_schedule("26.10", "ГР-1", [entry(1, teacher="Иванов И. И.")],
                           now=datetime(2026, 10, 26, 12, 0))
    assert "👤 Иванов И. И." in text


def test_format_today_with_state_tomorrow_without():
    entries = [entry(1), entry(2, date="26.10")]
    text_today = format_schedule("26.10", "ГР-1", entries,
                                 now=datetime(2026, 10, 26, 9, 0), with_state=True)
    assert "Сейчас:" in text_today
    text_tomorrow = format_schedule("26.10", "ГР-1", entries,
                                    now=datetime(2026, 10, 26, 9, 0), with_state=False)
    assert "Сейчас:" not in text_tomorrow


def test_format_empty_pairs_shown_with_emoji():
    text = format_schedule(
        "26.10", "ГР-1",
        [entry(1, subject=""), entry(2, subject=""), entry(3)],
        now=datetime(2026, 10, 26, 12, 0),
    )
    assert "1️⃣ <i>пара — окно</i>" in text
    assert "2️⃣ <i>пара — окно</i>" in text
    assert "3️⃣" in text
    assert "— нет" not in text
    assert "⏳" not in text


def test_format_max_room():
    text = format_schedule("26.10", "ГР-1", [entry(1, room="max", teacher="Иванов И. И.")],
                           now=datetime(2026, 10, 26, 12, 0))
    assert "🚪 пара в максе" in text
    assert "каб. max" not in text


def test_format_dash_separator():
    text = format_schedule("26.10", "ГР-1", [entry(1, room="304", teacher="Иванов И. И.")],
                           now=datetime(2026, 10, 26, 12, 0))
    assert "📚 Предмет\n—————\n🚪 каб. 304\n👤 Иванов И. И." in text
    # без кабинета и ФИО тире не рисуем
    text = format_schedule("26.10", "ГР-1", [entry(2, room="", teacher="")],
                           now=datetime(2026, 10, 26, 12, 0))
    assert "—————" not in text


def test_notification_has_start_line_not_state():
    entries = [entry(1), entry(2)]
    text = format_notification("26.10", "ГР-1", entries, now=datetime(2026, 10, 26, 9, 0))
    assert "Начало занятий в 08:30, всего 2 пар" in text
    assert "Сейчас:" not in text


def test_what_now_states():
    # ongoing: 9:00 пн, 1 пара идёт
    text = format_what_now("26.10", "ГР-1", [entry(1), entry(2)],
                           now=datetime(2026, 10, 26, 9, 0))
    assert "Сейчас:</b> 1 пара" in text and "До конца 60 мин" in text
    # break: 10:05
    text = format_what_now("26.10", "ГР-1", [entry(1), entry(2)],
                           now=datetime(2026, 10, 26, 10, 5))
    assert "Перемена" in text and "Дальше: 2 пара" in text
    # before: 07:30
    text = format_what_now("26.10", "ГР-1", [entry(1)],
                           now=datetime(2026, 10, 26, 7, 30))
    assert "Занятия начнутся в 08:30" in text
    # after: 20:00
    text = format_what_now("26.10", "ГР-1", [entry(1)],
                           now=datetime(2026, 10, 26, 20, 0))
    assert "закончились" in text
    # empty
    text = format_what_now("26.10", "ГР-1", [], now=datetime(2026, 10, 26, 12, 0))
    assert "пар нет" in text


def test_what_now_max_room():
    text = format_what_now("26.10", "ГР-1", [entry(1, room="max", teacher="")],
                           now=datetime(2026, 10, 26, 9, 0))
    assert "Сейчас:</b> 1 пара — Предмет, пара в максе" in text


def test_split_message_long():
    entries = [entry(i, room=str(100 + i), teacher="Преподаватель") for i in range(1, 320)]
    text = format_schedule("26.10", "ГР-1", entries, now=datetime(2026, 10, 26, 12, 0))
    assert len(text) > 4096
    chunks = split_message(text)
    assert len(chunks) > 1
    assert all(len(c) <= 4096 for c in chunks)
    assert "\n\n".join(chunks) == text  # ничего не обрезано и не потеряно
