"""空き判定エンジン（学校非依存の純粋関数）.

現行 ``nust-room-search`` の ``index()`` 内ロジック
（指定 曜日×時限×有効学期 の使用中教室集合を作り、全教室から差集合を取る）を、
校舎別 ``if`` 分岐を撤去して学校非依存に一般化したもの（DESIGN.md §8-2）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Lesson:
    """時間割の 1 コマ（``schedule.csv`` の 1 行）."""

    term: str
    day: str
    period: int
    room: str
    building: str
    department: str = ""
    course: str = ""


@dataclass(frozen=True)
class Room:
    """教室マスタの 1 室（``classrooms.csv`` の 1 行）."""

    room: str
    building: str


def occupied_rooms(
    lessons: Iterable[Lesson], *, day: str, period: int, active_terms: Sequence[str]
) -> set[str]:
    """指定 曜日×時限 に、有効学期のいずれかで授業が入っている教室名の集合."""
    active = set(active_terms)
    return {
        lesson.room
        for lesson in lessons
        if lesson.day == day and lesson.period == period and lesson.term in active
    }


def free_rooms(
    lessons: Iterable[Lesson],
    rooms: Iterable[Room],
    *,
    day: str,
    period: int,
    active_terms: Sequence[str],
    building_order: Sequence[str] | None = None,
    building: str | None = None,
) -> list[Room]:
    """指定 曜日×時限 に空いている教室を返す.

    Args:
        lessons: 学校の時間割（全コマ）。
        rooms: 学校の全教室（母集合）。
        day: 曜日（config の ``days`` のいずれか）。
        period: 時限（config の ``periods[].no`` のいずれか）。
        active_terms: 有効な学期 id の一覧（:func:`roomradar.terms.active_terms`）。
        building_order: 表示・ソート順に使う校舎名の並び（config の定義順）。
        building: 指定すると、その校舎名の教室だけに絞り込む。

    Returns:
        空き教室の一覧。``building_order`` → 教室名 の順でソート済み。
    """
    occupied = occupied_rooms(lessons, day=day, period=period, active_terms=active_terms)
    order = {name: i for i, name in enumerate(building_order or [])}
    fallback = len(order)  # 並びに無い校舎は末尾へ

    candidates = [
        room
        for room in rooms
        if room.room not in occupied and (building is None or room.building == building)
    ]
    candidates.sort(key=lambda r: (order.get(r.building, fallback), r.room))
    return candidates
