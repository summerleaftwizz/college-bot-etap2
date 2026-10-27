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
class Lesson:
    lesson_number: int
    time: str
    subject: str
    room: str
    teacher: str = ""
    # Подгруппы: [{"room": "121", "teacher": "Платицына Е. В."}, ...]
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


def _is_fio(value: str) -> bool:
    """Похоже ли на ФИО: 'Платицына Е. В.', 'Байшева Я.В.', 'Иванов Иван'."""
    words = value.split()
    if not 2 <= len(words) <= 4:
        return False
    # слово: фамилия/имя ИЛИ инициал («Е.»)
    word = r"^[А-ЯЁA-Z](?:[А-ЯЁа-яёA-Za-z-]+\.?|\.)$"
    return all(re.match(word, w) for w in words)


def _extract_subgroups(
    df, r: int, sc: int, rc: int, block_end: int, lesson_col: int, cfg: ParserConfig,
    max_col: int = 0,
) -> list[dict]:
    """Ищет подгруппы в строке пары: соседние ячейки с кабинетами и ФИО.

    Формат «английского языка»: после ячейки предмета в той же строке идут
    кабинеты и фамилии преподавателей подгрупп (например ауд. 121 + ФИО1 +
    ФИО2), плюс строка преподавателей под самой парой. Всё читаем из ячеек
    динамически — ничего не хардкодим. Окно ограничено колонкой следующей
    группы (max_col), чтобы не захватывать чужие данные.
    """
    ncols = df.shape[1]
    if max_col:
        ncols = min(ncols, max_col)
    # окно ячеек правее предмета в строке пары (кабинеты подгрупп и ФИО)
    cells: list[str] = []
    for c in range(rc, min(rc + 4, ncols)):
        v = _cell_to_str(df.iat[r, c])
        if v and not _is_group_name(v, cfg):
            cells.append(v)
    # строка преподавателей под парой — ФИО подгрупп в тех же колонках
    if r + 1 < block_end and _to_int(df.iat[r + 1, lesson_col]) is None:
        for c in range(rc, min(rc + 4, ncols)):
            v = _normalize_teacher(df.iat[r + 1, c])
            if v and _is_fio(v):
                cells.append(v)

    # раскладываем по подгруппам: кабинет открывает подгруппу, ФИО —
    # преподаватель текущей (или новой, если кабинета нет)
    subs: list[dict] = []
    for v in cells:
        if _is_fio(v):
            if not subs or subs[-1].get("teacher"):
                subs.append({"room": "", "teacher": v})
            else:
                subs[-1]["teacher"] = v
        else:
            if subs and not subs[-1].get("room"):
                subs[-1]["room"] = v
            elif subs and not subs[-1].get("teacher"):
                subs[-1]["teacher"] = v
            else:
                subs.append({"room": v, "teacher": ""})
    return [s for s in subs if s["room"] or s["teacher"]]


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
                room = _cell_to_str(df.iat[r, rc])
                teacher = ""
                subgroups: list[dict] = []
                if r + 1 < block_end and _to_int(df.iat[r + 1, lesson_col]) is None:
                    # следующая строка — ФИО преподавателя (в колонке предмета)
                    teacher = _normalize_teacher(df.iat[r + 1, sc])
                    # подгруппы: соседние ячейки с кабинетами/ФИО (английский и др.)
                    next_sc = pairs[gi + 1][0] if gi + 1 < len(pairs) else 0
                    subgroups = _extract_subgroups(
                        df, r, sc, rc, block_end, lesson_col, cfg, max_col=next_sc
                    )
                    if len(subgroups) == 1:
                        s0 = subgroups[0]
                        # одиночный «кабинет = основной», без своего ФИО —
                        # это обычная пара, а не подгруппа
                        same = (s0.get("room") or "") == room and (
                            s0.get("teacher") or ""
                        ) in ("", teacher)
                        if same:
                            subgroups = []  # обычный предмет, не подгруппы
                if subgroups:
                    # подгруппы найдены: основной кабинет/ФИО уходят в список,
                    # чтобы не дублироваться
                    groups.setdefault(name, []).append(
                        Lesson(
                            lesson_number=lesson_number,
                            time="",
                            subject=subject,
                            room="",
                            teacher="",
                            subgroups=subgroups,
                        )
                    )
                else:
                    groups.setdefault(name, []).append(
                        Lesson(lesson_number=lesson_number, time="", subject=subject, room=room, teacher=teacher)
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
