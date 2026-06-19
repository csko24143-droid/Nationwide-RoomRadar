"""設定＋データを束ねた「1 校分のロード済みモデル」.

``LoadedSchool.load("nust")`` で ``schools/nust/`` の config.yml・schedule.csv・
classrooms.csv を読み込み、空き判定（:func:`roomradar.availability.free_rooms`）と
有効学期判定（:func:`roomradar.terms.active_terms`）を学校の設定に沿って呼び出せる。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from .availability import Lesson, Room, free_rooms
from .config import SchoolConfig, load_school_config
from .data import load_lessons, load_rooms_or_derive
from .terms import active_terms

DEFAULT_SCHOOLS_DIR = Path("schools")

# 曜日名 → Python の weekday()（0=月 … 6=日）
_JP_WEEKDAY = {"月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6}


def _tzinfo(timezone: str) -> datetime.tzinfo:
    """設定のタイムゾーン名から tzinfo を得る.

    ``zoneinfo`` のデータが無い環境でも動くよう、日本（DST なし・固定 +9）は
    固定オフセットにフォールバックする。
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: WPS433 (stdlib, 3.9+)

        return ZoneInfo(timezone)
    except Exception:  # noqa: BLE001 (tzdata 未導入などはフォールバック)
        if timezone in ("Asia/Tokyo", "Japan", "JST"):
            return datetime.timezone(datetime.timedelta(hours=9))
        return datetime.timezone.utc


@dataclass
class LoadedSchool:
    """1 校分の設定とデータ（イミュータブルに扱う想定）."""

    config: SchoolConfig
    lessons: list[Lesson]
    rooms: list[Room]

    # --- 読み込み ----------------------------------------------------------
    @classmethod
    def load(cls, slug: str, base_dir: str | Path = DEFAULT_SCHOOLS_DIR) -> "LoadedSchool":
        """``<base_dir>/<slug>/`` から 1 校分を読み込む."""
        school_dir = Path(base_dir) / slug
        config = load_school_config(school_dir / "config.yml")
        if config.slug != slug:
            raise ValueError(
                f"{school_dir}/config.yml の slug='{config.slug}' がフォルダ名 '{slug}' と一致しません"
            )
        lessons = load_lessons(school_dir / "schedule.csv")
        rooms = load_rooms_or_derive(school_dir / "classrooms.csv", lessons)
        return cls(config=config, lessons=lessons, rooms=rooms)

    # --- 時刻ヘルパ --------------------------------------------------------
    def now(self) -> datetime.datetime:
        """学校のタイムゾーンでの現在時刻."""
        return datetime.datetime.now(_tzinfo(self.config.timezone))

    def current_term_ids(self, today: datetime.date | None = None) -> list[str]:
        """``today``（既定: 学校TZの今日）に有効な学期 id."""
        if today is None:
            today = self.now().date()
        return active_terms(self.config.terms, today)

    def current_day_period(self, now: datetime.datetime | None = None) -> tuple[str, int]:
        """現在の曜日と時限を推定する（検索フォームの初期値用）.

        曜日が開講曜日外（例: 日曜）なら先頭の開講曜日に丸める。
        どの時限にも当てはまらない時刻なら先頭の時限を返す。
        """
        if now is None:
            now = self.now()
        weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
        day = weekday_names[now.weekday()]
        if day not in self.config.days:
            day = self.config.days[0]

        hhmm = now.strftime("%H:%M")
        period = self.config.periods[0].number
        for p in self.config.periods:
            if p.start <= hhmm <= p.end:
                period = p.number
                break
        return day, period

    def period_end(
        self, day: str, period: int, now: datetime.datetime | None = None
    ) -> datetime.datetime:
        """指定 曜日×時限 の「今週の終了日時」（予約・報告の失効時刻に使う）.

        旧 ``period_end_dt`` を学校設定（時限終了時刻＋タイムゾーン）に一般化したもの。
        """
        if now is None:
            now = self.now()
        p = self.config.period(period)
        if p is None:
            raise ValueError(f"未知の時限です: {period}")
        target_wd = _JP_WEEKDAY.get(day, 0)
        delta = (target_wd - now.weekday()) % 7
        target = (now + datetime.timedelta(days=delta)).date()
        hour, minute = (int(x) for x in p.end.split(":"))
        return datetime.datetime(
            target.year, target.month, target.day, hour, minute, tzinfo=now.tzinfo
        )

    # --- 空き判定 ----------------------------------------------------------
    def free_rooms(
        self,
        day: str,
        period: int,
        *,
        building: str | None = None,
        today: datetime.date | None = None,
    ) -> list[Room]:
        """指定 曜日×時限 の空き教室（学校の設定に沿ってソート済み）.

        有効学期は ``today``（既定: 学校TZの今日）から自動判定する。
        """
        return self.free_rooms_with_terms(
            day,
            period,
            active_terms=self.current_term_ids(today),
            building=building,
        )

    def free_rooms_with_terms(
        self,
        day: str,
        period: int,
        *,
        active_terms: list[str],
        building: str | None = None,
    ) -> list[Room]:
        """有効学期を明示指定して空き教室を求める（回帰検証・特定学期の照会用）."""
        return free_rooms(
            self.lessons,
            self.rooms,
            day=day,
            period=period,
            active_terms=active_terms,
            building_order=self.config.building_names,
            building=building,
        )
