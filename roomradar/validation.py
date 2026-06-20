"""学校データ（schedule.csv / classrooms.csv）の検証（DESIGN.md §7.2・data-import-format §3）.

config.yml の定義集合（term / day / period / building 名）と突き合わせ、表記ゆれ・
列不足・重複を検出する。CLI（``scripts/validate.py``）と管理UI（``/admin``）の双方から使う。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .config import ConfigError, load_school_config

REQUIRED_SCHEDULE_COLUMNS = {"term", "day", "period", "room", "building"}
REQUIRED_CLASSROOM_COLUMNS = {"room", "building"}


def validate_school(slug: str, schools_dir: str | Path) -> tuple[list[str], list[str]]:
    """1 校分を検証し、(errors, warnings) を返す。errors が空なら取り込み可."""
    errors: list[str] = []
    warnings: list[str] = []
    school_dir = Path(schools_dir) / slug

    try:
        cfg = load_school_config(school_dir / "config.yml")
    except (FileNotFoundError, ConfigError) as exc:
        return [f"config.yml: {exc}"], []

    term_ids = {t.id for t in cfg.terms}
    days = set(cfg.days)
    periods = set(cfg.period_numbers)
    buildings = set(cfg.building_names)

    schedule = school_dir / "schedule.csv"
    if not schedule.exists():
        errors.append("schedule.csv がありません（必須）")
    else:
        _validate_schedule(schedule, term_ids, days, periods, buildings, errors, warnings)

    classrooms = school_dir / "classrooms.csv"
    if classrooms.exists():
        _validate_classrooms(classrooms, buildings, errors, warnings)

    return errors, warnings


def _validate_schedule(path, term_ids, days, periods, buildings, errors, warnings) -> None:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = {h.strip() for h in (reader.fieldnames or [])}
        missing = REQUIRED_SCHEDULE_COLUMNS - header
        if missing:
            errors.append(f"schedule.csv: 必須列が不足: {sorted(missing)}")
            return

        seen: set[tuple] = set()
        dup_count = 0
        dup_examples: list[str] = []
        rows = 0
        for i, row in enumerate(reader, start=2):
            rows += 1
            term = (row.get("term") or "").strip()
            day = (row.get("day") or "").strip()
            period_raw = (row.get("period") or "").strip()
            room_raw = row.get("room") or ""
            room = room_raw.strip()
            building = (row.get("building") or "").strip()

            if term not in term_ids:
                errors.append(f"schedule.csv:{i}: term '{term}' は config に未定義 {sorted(term_ids)}")
            if day not in days:
                errors.append(f"schedule.csv:{i}: day '{day}' は config の days 外 {sorted(days)}")
            if not period_raw.isdigit() or int(period_raw) not in periods:
                errors.append(f"schedule.csv:{i}: period '{period_raw}' は config の periods 外 {sorted(periods)}")
            if building not in buildings:
                errors.append(
                    f"schedule.csv:{i}: building '{building}' が config の建物名と不一致（表記ゆれ?） {sorted(buildings)}"
                )
            if not room:
                errors.append(f"schedule.csv:{i}: room が空です")
            elif room != room_raw:
                warnings.append(f"schedule.csv:{i}: room '{room_raw}' に前後空白（'{room}' へ正規化推奨）")

            key = (term, day, period_raw, room)
            if key in seen:
                dup_count += 1
                if len(dup_examples) < 3:
                    dup_examples.append(f"schedule.csv:{i}: 重複 (term,day,period,room)={key}")
            seen.add(key)

        if dup_count:
            warnings.extend(dup_examples)
            warnings.append(
                f"schedule.csv: 同一 (term,day,period,room) の重複が計 {dup_count} 件"
                "（複数科目の相部屋・プレースホルダ等。空き判定には影響しません）"
            )
        if rows == 0:
            warnings.append("schedule.csv: データ行が 0 件です")


def _validate_classrooms(path, buildings, errors, warnings) -> None:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = {h.strip() for h in (reader.fieldnames or [])}
        missing = REQUIRED_CLASSROOM_COLUMNS - header
        if missing:
            errors.append(f"classrooms.csv: 必須列が不足: {sorted(missing)}")
            return
        seen: set[str] = set()
        for i, row in enumerate(reader, start=2):
            room = (row.get("room") or "").strip()
            building = (row.get("building") or "").strip()
            if not room:
                errors.append(f"classrooms.csv:{i}: room が空です")
            if building not in buildings:
                errors.append(
                    f"classrooms.csv:{i}: building '{building}' が config の建物名と不一致 {sorted(buildings)}"
                )
            if room and room in seen:
                warnings.append(f"classrooms.csv:{i}: 教室 '{room}' が重複")
            seen.add(room)
