#!/usr/bin/env python3
"""NUST（日大理工）の ``schedule_final.db`` を CSV テナントデータへ書き出す.

DESIGN.md §13「移行計画」の手順 1（DB→CSV エクスポート）と手順 3（旧実装との
回帰一致確認）を 1 本にまとめたもの。旧 ``nust-room-search`` リポジトリの
``schedule_final.db`` を入力に、``schools/nust/schedule.csv`` と
``schools/nust/classrooms.csv`` を生成する。

使い方::

    python scripts/export_nust.py --db /path/to/schedule_final.db --check

``--check`` を付けると、生成した CSV を新エンジンで読んだ空き判定が、
旧 ``app.py`` の SQL ロジックと全 曜日×時限 で一致するかを検証する。
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

# リポジトリ直下を import パスに追加（スクリプト直接実行のため）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roomradar.school import LoadedSchool  # noqa: E402

# 旧 app.py の現行挙動に合わせた既定（DESIGN §2.4 / §13）。
# 旧 index() は定数 ACTIVE_TERMS=['前期','通年'] で問い合わせていた。
LIVE_ACTIVE_TERMS = ["前期", "通年"]
DAYS = ["月", "火", "水", "木", "金", "土"]
PERIODS = [1, 2, 3, 4, 5, 6]
# 旧実装のソート: タワースコラ → 駿河台校舎 → （その他）→ 教室名
BUILDING_ORDER = ["タワースコラ", "駿河台校舎", "船橋校舎"]


def export(db_path: Path, out_dir: Path) -> tuple[int, int]:
    """DB から schedule.csv / classrooms.csv を書き出し、(行数, 教室数) を返す."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        schedule_rows = con.execute(
            "SELECT 学科, 履修期名, 曜日, 時限, 教室, 校舎, 科目名 "
            "FROM schedules ORDER BY 履修期名, 曜日, 時限, 校舎, 教室"
        ).fetchall()
        classroom_rows = con.execute(
            "SELECT name, building FROM classrooms ORDER BY building, name"
        ).fetchall()
    finally:
        con.close()

    schedule_csv = out_dir / "schedule.csv"
    with schedule_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["department", "term", "day", "period", "room", "building", "course"])
        for r in schedule_rows:
            writer.writerow(
                [r["学科"], r["履修期名"], r["曜日"], r["時限"], r["教室"], r["校舎"], r["科目名"]]
            )

    classrooms_csv = out_dir / "classrooms.csv"
    with classrooms_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["room", "building"])
        for r in classroom_rows:
            writer.writerow([r["name"], r["building"]])

    return len(schedule_rows), len(classroom_rows)


def _old_free_rooms(db_path: Path, day: str, period: int) -> list[str]:
    """旧 app.py の index() ロジックを SQL で忠実に再現し、空き教室名を返す."""
    con = sqlite3.connect(db_path)
    try:
        ph = ",".join("?" * len(LIVE_ACTIVE_TERMS))
        occupied = {
            str(row[0])
            for row in con.execute(
                f"SELECT 教室 FROM schedules WHERE 曜日=? AND 時限=? AND 履修期名 IN ({ph})",
                [day, period, *LIVE_ACTIVE_TERMS],
            )
        }
        all_rooms = con.execute("SELECT name, building FROM classrooms").fetchall()
    finally:
        con.close()
    empty = [
        {"name": n, "building": b} for (n, b) in all_rooms if str(n) not in occupied
    ]
    empty.sort(
        key=lambda x: (
            x["building"] != "タワースコラ",
            x["building"] != "駿河台校舎",
            x["name"],
        )
    )
    return [e["name"] for e in empty]


def check_equivalence(db_path: Path, out_dir: Path) -> bool:
    """新エンジン（CSV）と旧ロジック（DB）の空き判定が全コマで一致するか検証."""
    school = LoadedSchool.load("nust", base_dir=out_dir.parent)
    mismatches = 0
    for day in DAYS:
        for period in PERIODS:
            new = [
                r.room
                for r in school.free_rooms_with_terms(
                    day, period, active_terms=LIVE_ACTIVE_TERMS
                )
            ]
            old = _old_free_rooms(db_path, day, period)
            if new != old:
                mismatches += 1
                print(f"  ✗ {day}{period}限: new={len(new)} 室 / old={len(old)} 室 不一致")
    if mismatches == 0:
        print(f"  ✓ 全 {len(DAYS) * len(PERIODS)} コマで旧実装と一致")
    return mismatches == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="schedule_final.db のパス")
    parser.add_argument(
        "--out", type=Path, default=Path("schools/nust"), help="出力先ディレクトリ"
    )
    parser.add_argument("--check", action="store_true", help="旧実装との一致を検証する")
    args = parser.parse_args(argv)

    if not args.db.exists():
        parser.error(f"DB が見つかりません: {args.db}")

    n_sched, n_rooms = export(args.db, args.out)
    print(f"書き出し完了: schedule.csv={n_sched} 行 / classrooms.csv={n_rooms} 室 → {args.out}")

    if args.check:
        print("旧実装との回帰一致を検証中…")
        if not check_equivalence(args.db, args.out):
            print("不一致あり。ロジックを確認してください。", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
