"""Парсер Excel-расписания (реальный формат колледжа).

Формат файла (проверено на реальных данных):
  * один .xlsx = одна дата; лист(ы) называются по дню недели;
  * группы идут горизонтальными блоками (по несколько в ряд), а блоки —
    друг под другом:
        Пара | Дисциплина (гр.1) ... | Ауд. (гр.1) ... | Дисциплина (гр.2) ...
        №    | Преподаватель        |                 | ...
             | 1  2  3 (подгруппы)  |                 | ...
             | 1ОГР-26-9 | ...      |                 | ...
        1    | История  | ...       | 304 | ...       | ...
        2    | ...      | ...       | ... | ...       | ...
  * колонка 0 = номер пары; строки с ФИО преподавателя чередуются со строками
    пар и пропускаются (в колонке 0 пусто);
  * у каждой группы две колонки: предмет (заголовок «Дисциплина»/«Предмет»)
    и кабинет (заголовок «Ауд.»/«Кабинет»).

Колонки находятся по синонимам из config.ParserConfig, названия групп — по
regex GROUP_NAME_PATTERN.
"""
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from config import ParserConfig

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


@dataclass
class SubgroupInfo:
    """Одна подгруппа пары: номер, аудитория и преподаватель из ячеек строки."""

    number: int
    room: Optional[str] = None
    teacher: Optional[str] = None


@dataclass
class Lesson:
    lesson_number: int
    time: str
    subject: str
    room: str
    teacher: str = ""
    # Полный список подгрупп (для пар с разбивкой, например «Иностранный язык»).
    subgroups: list = field(default_factory=list)


def _cell_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _to_int(value) -> Optional[int]:
    s = re.sub(r"[^\d]", "", _cell_to_str(value))
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _normalize_teacher(value) -> str:
    """Нормализует ФИО: схлопывает пробелы/табы/переносы строк в один пробел."""
    s = _cell_to_str(value)
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _matches_synonym(value: str, synonyms: tuple) -> bool:
    for syn in synonyms:
        if value == syn:
            return True
    for syn in synonyms:
        if syn and syn in value:
            return True
    return False


def _find_columns(df: pd.DataFrame, cfg: ParserConfig) -> tuple[int, list[int], list[int]]:
    """Возвращает (колонка номера пары, [колонки предметов], [колонки кабинетов])."""
    ncols = df.shape[1]
    scan = min(cfg.HEADER_SCAN_ROWS, len(df))
    lesson_col: Optional[int] = None
    subject_cols: list[int] = []
    room_cols: list[int] = []

    for r in range(scan):
        for c in range(ncols):
            v = _cell_to_str(df.iat[r, c]).lower()
            if not v:
                continue
            if lesson_col is None and _matches_synonym(v, cfg.LESSON_NUM_SYNONYMS):
                lesson_col = c
            if _matches_synonym(v, cfg.SUBJECT_SYNONYMS) and c not in subject_cols:
                subject_cols.append(c)
            if _matches_synonym(v, cfg.ROOM_SYNONYMS) and c not in room_cols:
                room_cols.append(c)

    subject_cols.sort()
    room_cols.sort()

    if lesson_col is None:
        lesson_col = 0

    if not subject_cols:
        # фолбэк: колонки заданы индексами в config
        if isinstance(cfg.COL_SUBJECT, int):
            lesson_col = cfg.COL_LESSON_NUM if isinstance(cfg.COL_LESSON_NUM, int) else 0
            subject_cols = [cfg.COL_SUBJECT]
            room_cols = [cfg.COL_ROOM] if isinstance(cfg.COL_ROOM, int) else []
        else:
            raise ParseError("не найдены колонки предмета (Дисциплина/Предмет)")

    return lesson_col, subject_cols, room_cols


def _is_group_name(value: str, cfg: ParserConfig) -> bool:
    return bool(value) and re.match(cfg.GROUP_NAME_PATTERN, value) is not None


# ФИО: «Кобзова С. В.», «Ощепкова А.С.», «Иванов Иван И.»
FIO_RE = re.compile(
    r"^[А-ЯЁA-Z][а-яёa-z\-]+(?:\s+[А-ЯЁA-Z][а-яёa-z\-]+)?"
    r"\s+[А-ЯЁA-Z]\.\s*[А-ЯЁA-Z]?\.?$"
)
# Аудитория: служебный префикс + номер («Ино 319» -> «319»)
ROOM_NUMBER_RE = re.compile(r"\d+\s*[A-Za-zА-Яа-я]?")


def _is_fio(value: str) -> bool:
    """Похоже ли на ФИО в формате «Фамилия И. О.» (значение — из ячейки)."""
    return bool(FIO_RE.match(_normalize_teacher(value)))


def _clean_room(value: str) -> str:
    """Убирает служебный префикс аудитории: «Ино 319» -> «319».

    Если цифр нет («Спортзал», «Акт. зал») — возвращает строку как есть.
    """
    s = _normalize_teacher(value)
    if not s:
        return ""
    m = ROOM_NUMBER_RE.search(s)
    return m.group(0).strip() if m else s


def _looks_like_data(value: str) -> bool:
    """Ячейка похожа на данные пары (аудитория с цифрами или ФИО),
    а не на название чужого предмета («Химия», «Математика»)."""
    if not value:
        return False
    if _is_fio(value):
        return True
    return any(ch.isdigit() for ch in value)


def _extract_subgroups(
    df, r: int, sc: int, block_end: int, lesson_col: int, cfg: ParserConfig,
    stop_cols: frozenset = frozenset(),
) -> list[SubgroupInfo]:
    """Собирает подгруппы из ВСЕХ ячеек строки справа от названия предмета.

    Формат: предмет | ауд. 1 | ФИО 1 | ауд. 2 | ФИО 2 | … — данные разных
    подгрупп лежат в одной строке в разных колонках. Функция проходит по
    всем колонкам до конца строки, классифицирует ячейки (ФИО или аудитория)
    и группирует их в пары по порядку следования. Ранних выходов нет:
    обрабатываются все пары, сколько бы их ни было.

    stop_cols — колонки предметов ДРУГИХ групп. На такой колонке сканирование
    прерывается, ЕСЛИ в ячейке лежит чужой предмет (текст без цифр и не ФИО).
    Если же там аудитория (есть цифры) или ФИО — это данные нашей пары,
    и чтение продолжается.
    """
    ncols = df.shape[1]
    has_teacher_row = (
        r + 1 < block_end and _to_int(df.iat[r + 1, lesson_col]) is None
    )
    values: list[str] = []
    empty_gap = 0
    boundary = ncols

    for c in range(sc + 1, ncols):
        cell = _cell_to_str(df.iat[r, c])
        if c in stop_cols and not _looks_like_data(cell):
            boundary = c
            break
        if cell and not _is_group_name(cell, cfg):
            values.append(cell)
            empty_gap = 0
            continue
        if has_teacher_row:
            fio = _normalize_teacher(df.iat[r + 1, c])
            if fio and _is_fio(fio):
                values.append(fio)
                empty_gap = 0
                continue
        empty_gap += 1
        if values and empty_gap > 3:
            boundary = c
            break

    # группировка: аудитория открывает подгруппу, ФИО идёт в текущую
    subs: list[SubgroupInfo] = []
    current: Optional[SubgroupInfo] = None

    def flush() -> None:
        nonlocal current
        if current is not None and (current.room or current.teacher):
            subs.append(current)
        current = None

    for value in values:
        if _is_fio(value):
            if current is not None and not current.teacher:
                current.teacher = value
            else:
                flush()
                current = SubgroupInfo(number=0, teacher=value)
        else:
            if current is not None and not current.room:
                current.room = _clean_room(value) or None
            else:
                flush()
                current = SubgroupInfo(number=0, room=_clean_room(value) or None)
    flush()

    # если преподаватель так и не нашёлся в строке — пробуем строку под парой
    if has_teacher_row and not any(s.teacher for s in subs):
        teachers = [
            _normalize_teacher(df.iat[r + 1, c]) for c in range(sc + 1, boundary)
        ]
        teachers = [t for t in teachers if t and _is_fio(t)]
        for i, t in enumerate(teachers):
            if i < len(subs) and not subs[i].teacher:
                subs[i].teacher = t

    for i, sub in enumerate(subs, 1):
        sub.number = i
    return subs


def _parse_sheet(
    df: pd.DataFrame, cfg: ParserConfig, lesson_col: int, subject_cols: list[int], room_cols: list[int]
) -> dict[str, list[Lesson]]:
    pairs = [
        (sc, room_cols[i] if i < len(room_cols) else sc + 4)
        for i, sc in enumerate(subject_cols)
    ]
    nrows = len(df)

    # строки-границы блоков (строки с названиями групп)
    block_rows: list[int] = []
    for r in range(nrows):
        for sc, _ in pairs:
            if _is_group_name(_cell_to_str(df.iat[r, sc]), cfg):
                block_rows.append(r)
                break

    if not block_rows:
        raise ParseError("не найдены названия групп на листе")

    groups: dict[str, list[Lesson]] = {}
    for bi, block_start in enumerate(block_rows):
        block_end = block_rows[bi + 1] if bi + 1 < len(block_rows) else nrows
        names = [_cell_to_str(df.iat[block_start, sc]) for sc, _ in pairs]

        for r in range(block_start + 1, block_end):
            lesson_number = _to_int(df.iat[r, lesson_col])
            if lesson_number is None:
                continue  # строка с ФИО преподавателя или пустая
            for gi, (sc, rc) in enumerate(pairs):
                name = names[gi]
                if not name:
                    continue
                subject = _cell_to_str(df.iat[r, sc])
                room = _clean_room(_cell_to_str(df.iat[r, rc]))
                teacher = ""
                if r + 1 < block_end and _to_int(df.iat[r + 1, lesson_col]) is None:
                    # следующая строка — ФИО преподавателя (в колонке предмета)
                    teacher = _normalize_teacher(df.iat[r + 1, sc])
                # подгруппы: все ячейки справа от предмета (иностранный язык и др.)
                stop_cols = frozenset(
                    other_sc for other_sc, _ in pairs[gi + 1:] if other_sc > sc
                )
                subgroups = _extract_subgroups(
                    df, r, sc, block_end, lesson_col, cfg, stop_cols=stop_cols
                )
                # разбивка на подгруппы — только если пар две и больше
                if len(subgroups) >= 2:
                    # обратная совместимость: room/teacher — данные 1-й подгруппы
                    room = subgroups[0].room or room
                    teacher = subgroups[0].teacher or teacher
                elif len(subgroups) == 1:
                    # одна пара: обычный формат, поля берём из неё
                    room = subgroups[0].room or room
                    teacher = subgroups[0].teacher or teacher
                    subgroups = []
                else:
                    subgroups = []
                groups.setdefault(name, []).append(
                    Lesson(
                        lesson_number=lesson_number,
                        time="",
                        subject=subject,
                        room=room,
                        teacher=teacher,
                        subgroups=subgroups,
                    )
                )
    return groups


def parse_schedule(content: bytes, cfg: ParserConfig) -> dict[str, list[Lesson]]:
    """Парсит xlsx. Возвращает {группа: [Lesson, ...]}."""
    try:
        excel = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
    except Exception as exc:
        raise ParseError(f"не удалось открыть Excel: {exc}") from exc

    groups: dict[str, list[Lesson]] = {}
    errors: list[str] = []
    for sheet_name in excel.sheet_names:
        try:
            df = pd.read_excel(excel, sheet_name=sheet_name, header=None, dtype=object)
            lesson_col, subject_cols, room_cols = _find_columns(df, cfg)
            sheet_groups = _parse_sheet(df, cfg, lesson_col, subject_cols, room_cols)
            for g, lessons in sheet_groups.items():
                groups.setdefault(g, []).extend(lessons)
        except Exception as exc:
            errors.append(f"{sheet_name}: {exc}")
            logger.warning("лист %s не распарсился: %s", sheet_name, exc)

    if not groups:
        raise ParseError("ни один лист не удалось распарсить: " + "; ".join(errors))
    return groups
