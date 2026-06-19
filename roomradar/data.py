"""``schedule.csv`` / ``classrooms.csv`` のローダ（DESIGN.md §5.3）.

列名は英語固定（``department,term,day,period,room,building,course`` /
``room,building``）。表記ゆれを避けるため前後空白は除去する。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .availability import Lesson, Room

SCHEDULE_COLUMNS = ["department", "term", "day", "period", "room", "building", "course"]
CLASSROOM_COLUMNS = ["room", "building"]


class DataError(ValueError):
    """CSV の内容が不正なときに送出する."""


def _clean(value: str | None) -> str:
    return (value or "").strip()


def load_lessons(path: str | Path) -> list[Lesson]:
    """``schedule.csv`` を読み込んで :class:`~roomradar.availability.Lesson` の一覧を返す."""
    path = Path(path)
    lessons: list[Lesson] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        _check_header(reader.fieldnames, {"term", "day", "period", "room", "building"}, path)
        for i, row in enumerate(reader, start=2):
            period_raw = _clean(row.get("period"))
            try:
                period = int(period_raw)
            except (TypeError, ValueError):
                raise DataError(f"{path}:{i}: period が整数ではありません: {period_raw!r}")
            lessons.append(
                Lesson(
                    term=_clean(row.get("term")),
                    day=_clean(row.get("day")),
                    period=period,
                    room=_clean(row.get("room")),
                    building=_clean(row.get("building")),
                    department=_clean(row.get("department")),
                    course=_clean(row.get("course")),
                )
            )
    return lessons


def load_rooms(path: str | Path) -> list[Room]:
    """``classrooms.csv`` を読み込んで :class:`~roomradar.availability.Room` の一覧を返す."""
    path = Path(path)
    rooms: list[Room] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        _check_header(reader.fieldnames, {"room", "building"}, path)
        for row in reader:
            room = _clean(row.get("room"))
            if not room:
                continue
            rooms.append(Room(room=room, building=_clean(row.get("building"))))
    return rooms


def derive_rooms(lessons: list[Lesson]) -> list[Room]:
    """時間割から (教室, 校舎) のユニーク集合を生成する.

    ``classrooms.csv`` が無い学校のフォールバック（DESIGN §5.3）。
    時間割に一度も登場しない常時空き教室は拾えない点に注意。
    """
    seen: dict[tuple[str, str], Room] = {}
    for lesson in lessons:
        key = (lesson.room, lesson.building)
        if lesson.room and key not in seen:
            seen[key] = Room(room=lesson.room, building=lesson.building)
    return list(seen.values())


def load_rooms_or_derive(classrooms_path: str | Path, lessons: list[Lesson]) -> list[Room]:
    """``classrooms.csv`` があれば読み、無ければ時間割から生成する."""
    path = Path(classrooms_path)
    if path.exists():
        return load_rooms(path)
    return derive_rooms(lessons)


def _check_header(fieldnames, required: set[str], path: Path) -> None:
    present = {f.strip() for f in (fieldnames or [])}
    missing = required - present
    if missing:
        raise DataError(f"{path}: 必須列が不足しています: {sorted(missing)}（ヘッダ: {sorted(present)}）")
