"""日付から「いま有効な学期」を求める純粋関数.

現行 ``nust-room-search`` の ``get_active_terms()`` を学校非依存に一般化したもの
（DESIGN.md §8-4）。学期の境界は ``config.yml`` の ``terms[].start/end``（``MM-DD``）
または ``always:true`` で与えられ、年跨ぎ（例: 後期 ``09-21``〜``03-31``）にも対応する。
"""

from __future__ import annotations

import datetime
from typing import Iterable

from .config import Term

MonthDay = tuple[int, int]


def _parse_md(value: str) -> MonthDay:
    month, day = value.split("-")
    return int(month), int(day)


def in_season(today: MonthDay, start: MonthDay, end: MonthDay) -> bool:
    """``today`` が ``start``〜``end``（両端含む）の期間内か.

    ``start <= end`` は通常の期間。``start > end`` は年末を跨ぐ期間とみなす
    （例: 後期 ``(9,21)``〜``(3,31)``）。
    """
    if start <= end:
        return start <= today <= end
    return today >= start or today <= end


def active_terms(terms: Iterable[Term], today: datetime.date | None = None) -> list[str]:
    """``today`` の時点で有効な学期 id の一覧を、config の定義順で返す.

    - ``always=True`` の学期（通年）は常に含む。
    - ``start``/``end`` を持つ学期は期間内のときだけ含む。
    """
    if today is None:
        today = datetime.date.today()
    md = (today.month, today.day)
    result: list[str] = []
    for term in terms:
        if term.always:
            result.append(term.id)
        elif term.start and term.end and in_season(md, _parse_md(term.start), _parse_md(term.end)):
            result.append(term.id)
    return result
