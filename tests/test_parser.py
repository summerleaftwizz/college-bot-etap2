"""Unit-тест парсера на фиктивном .xlsx в реальном формате (группы блоками)."""
import io

import pandas as pd
import pytest

from config import settings
from services.parser import ParseError, _normalize_teacher, parse_schedule


def make_xlsx() -> bytes:
    """Строит файл: колонка 0 = номер пары, по горизонтали группы,
    у каждой группы колонки «Дисциплина» и «Ауд.», строки ФИО чередуются."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # 12 колонок: 0=Пара, (1=Дисциплина, 5=Ауд.) — группа 1,
        # (7=Дисциплина, 11=Ауд.) — группа 2.
        df = pd.DataFrame(
            [
                ["Расписание на 26.10.2026", None, None, None, None, None, None, None, None, None, None, None],
                ["Пара", "Дисциплина", None, None, None, "Ауд.", None, "Дисциплина", None, None, None, "Ауд."],
                ["№", "Преподаватель", None, None, None, None, None, "Преподаватель", None, None, None, None],
                [None, 1, None, 2, None, 3, None, 1, None, 2, None, 3],
                [None, "1ОГР-26-9", None, None, None, None, None, "БУХ-26-9", None, None, None, None],
                [1, "История", None, None, None, "304", None, "Химия", None, None, None, "205"],
                [None, "Иванов  И.  И.", None, None, None, None, None, "Петров\nП. П.", None, None, None, None],
                [2, "Математика", None, None, None, "307", None, None, None, None, None, None],
                [None, "Иванов И. И.", None, None, None, None, None, None, None, None, None, None],
                [3, None, None, None, None, None, None, "Физика", None, None, None, "310"],
            ]
        )
        df.to_excel(writer, sheet_name="Понедельник", index=False, header=False)
    return buf.getvalue()


def test_parse_horizontal_groups():
    groups = parse_schedule(make_xlsx(), settings.parser)
    assert set(groups.keys()) == {"1ОГР-26-9", "БУХ-26-9"}

    g1 = groups["1ОГР-26-9"]
    assert [l.lesson_number for l in g1] == [1, 2, 3]
    assert g1[0].subject == "История" and g1[0].room == "304"
    assert g1[0].teacher == "Иванов И. И."  # лишние пробелы схлопнуты
    assert g1[1].subject == "Математика" and g1[1].room == "307"
    assert g1[1].teacher == "Иванов И. И."
    assert g1[2].subject == "" and g1[2].room == ""
    assert g1[2].teacher == ""  # последняя строка файла — ФИО нет

    g2 = groups["БУХ-26-9"]
    assert [l.lesson_number for l in g2] == [1, 2, 3]
    assert g2[0].subject == "Химия" and g2[0].room == "205"
    assert g2[0].teacher == "Петров П. П."  # перенос строки схлопнут
    assert g2[1].subject == "" and g2[1].room == ""
    assert g2[1].teacher == ""  # ФИО нет
    assert g2[2].subject == "Физика" and g2[2].room == "310"
    assert g2[2].teacher == ""


def test_normalize_teacher():
    assert _normalize_teacher("Иванов   И.  И.") == "Иванов И. И."
    assert _normalize_teacher("Петров\nП. П.\n") == "Петров П. П."
    assert _normalize_teacher(None) == ""
    assert _normalize_teacher("   ") == ""


def test_group_pattern_accepts_english_subgroups():
    """Подгруппы латиницей: 1ИСИП-25-9A и т.п."""
    pat = settings.parser.GROUP_NAME_PATTERN
    assert __import__("re").match(pat, "1ИСИП-25-9A")
    assert __import__("re").match(pat, "1ИСИП-25-9B")
    assert __import__("re").match(pat, "ОПИр-25-9C")
    assert __import__("re").match(pat, "1ОГР-26-9")
    assert not __import__("re").match(pat, "Иванов И.И.")


def test_is_fio_patterns():
    """ФИО-детект: разные фамилии, никакой хардкод."""
    from services.parser import _is_fio
    assert _is_fio("Платицына Е. В.")
    assert _is_fio("Байшева Я. В.")
    assert _is_fio("Ощепкова А. С.")
    assert _is_fio("Грабанова И. И.")
    assert _is_fio("Petrov A. B.")
    assert not _is_fio("121")
    assert not _is_fio("Иностранный язык")
    assert not _is_fio("каб. 304")


def test_extract_subgroups_from_row():
    """Реальная строка: предмет | ауд.1 | ФИО1 | ауд.2 | ФИО2 → 2 подгруппы."""
    import pandas as pd
    from services.parser import ParserConfig, _extract_subgroups
    df = pd.DataFrame(
        [
            ["Иностранный язык в профессиональной деятельности",
             "Ино... 319", "Кобзова С. В.", "Ино... 202", "Ощепкова А. С."],
        ],
        dtype=object,
    )
    cfg = ParserConfig()
    subs = _extract_subgroups(df, 0, sc=0, rc=1, block_end=1, lesson_col=0, cfg=cfg)
    assert len(subs) == 2, subs
    assert subs[0]["room"] == "Ино... 319" and subs[0]["teacher"] == "Кобзова С. В."
    assert subs[1]["room"] == "Ино... 202" and subs[1]["teacher"] == "Ощепкова А. С."


def test_extract_subgroups_single_column_empty():
    """Вторая подгруппа пустая → одна подгруппа (кабинет + ФИО)."""
    import pandas as pd
    from services.parser import ParserConfig, _extract_subgroups
    df = pd.DataFrame(
        [["Иностранный язык", "Ино... 319", "Кобзова С. В.", None, None]],
        dtype=object,
    )
    cfg = ParserConfig()
    subs = _extract_subgroups(df, 0, sc=0, rc=1, block_end=1, lesson_col=0, cfg=cfg)
    assert len(subs) == 1
    assert subs[0]["room"] == "Ино... 319" and subs[0]["teacher"] == "Кобзова С. В."


def test_extract_subgroups_not_bleed_into_next_group():
    """Окно подгрупп не заезжает в колонки следующей группы."""
    import pandas as pd
    from services.parser import ParserConfig, _extract_subgroups
    # col0 - предмет гр.1, col1 - каб. гр.1, col2 - предмет гр.2 ("Химия"), col3 - каб. гр.2
    df = pd.DataFrame(
        [
            ["Иностранный язык", "304", "Химия", "201"],
        ],
        dtype=object,
    )
    cfg = ParserConfig()
    subs = _extract_subgroups(df, 0, sc=0, rc=1, block_end=1, lesson_col=0, cfg=cfg, max_col=2)
    # только кабинет 304, «Химия» не захвачена
    assert len(subs) == 1
    assert subs[0]["room"] == "304"
    assert not subs[0]["teacher"]


def test_parse_full_lesson_with_two_subgroups():
    """Сквозной тест: пара с двумя подгруппами из xlsx-строки."""
    import pandas as pd
    from services.parser import parse_schedule
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df = pd.DataFrame(
            [
                ["Пара", "Дисциплина", None, None, None, None, "Ауд."],
                ["№", "Преподаватель", None, None, None, None, None],
                [None, "1ИСИП-25-9", None, None, None, None, None],
                [3, "Иностранный язык в профессиональной деятельности",
                 "Ино... 319", "Кобзова С. В.", "Ино... 202", "Ощепкова А. С.", None],
            ]
        )
        df.to_excel(writer, sheet_name="Понедельник", index=False, header=False)
    groups = parse_schedule(buf.getvalue(), settings.parser)
    lessons = groups["1ИСИП-25-9"]
    assert len(lessons) == 1
    subs = lessons[0].subgroups
    assert len(subs) == 2, subs
    assert subs[0]["room"] == "Ино... 319" and subs[0]["teacher"] == "Кобзова С. В."
    assert subs[1]["room"] == "Ино... 202" and subs[1]["teacher"] == "Ощепкова А. С."
    assert lessons[0].room == "" and lessons[0].teacher == ""


def test_parse_raises_on_unknown_format():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame({"foo": [1, 2, 3]}).to_excel(writer, sheet_name="S", index=False)
    with pytest.raises(ParseError):
        parse_schedule(buf.getvalue(), settings.parser)
