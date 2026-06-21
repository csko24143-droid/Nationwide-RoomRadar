#!/usr/bin/env python3
"""静的コアのビルド：学校データを配信用のコンパクト JSON へ変換する（DESIGN.md §4.1 / §7.2）.

各校の ``config.yml`` ＋ ``schedule.csv`` ＋ ``classrooms.csv`` を読み込み、
ブラウザが空き判定を**クライアント側で**計算できる JSON（``dist/schools/<slug>.json``）
と、全国レジストリ（``dist/index.json``）を出力する。

これにより検索機能は CDN 配信＋クライアント計算でスケールし、学校が増えても
サーバ負荷はほぼ増えない（動的レイヤ＝予約・報告だけがサーバを使う）。

    python scripts/build.py            # schools/ → dist/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roomradar.config import load_registry, visible_schools  # noqa: E402
from roomradar.school import LoadedSchool  # noqa: E402


def build_school_payload(school: LoadedSchool) -> dict:
    """1 校分の配信用 JSON（dict）を組み立てる."""
    cfg = school.config

    # occupied[term][day][str(period)] = ソート済みユニーク教室名
    occ: dict[str, dict[str, dict[str, set]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set))
    )
    for lesson in school.lessons:
        occ[lesson.term][lesson.day][str(lesson.period)].add(lesson.room)
    occupied = {
        term: {day: {p: sorted(rooms) for p, rooms in days.items()} for day, days in terms.items()}
        for term, terms in occ.items()
    }

    return {
        "slug": cfg.slug,
        "name": cfg.name,
        "short_name": cfg.short_name,
        "region": cfg.region,
        "accent": cfg.accent,
        "timezone": cfg.timezone,
        "disclaimer": cfg.disclaimer,
        "data_updated": cfg.data_updated,
        "source": cfg.source,
        "days": list(cfg.days),
        "periods": [{"period": p.number, "start": p.start, "end": p.end} for p in cfg.periods],
        "terms": [
            {k: v for k, v in {"id": t.id, "start": t.start, "end": t.end, "always": t.always}.items()
             if v not in (None, False)}
            for t in cfg.terms
        ],
        "buildings": [{"id": b.id, "name": b.name, "color": b.color} for b in cfg.buildings],
        "rooms": [{"room": r.room, "building": r.building} for r in school.rooms],
        "occupied": occupied,
    }


def school_stats(school: LoadedSchool, ref) -> dict:
    """ダッシュボード用の静的統計（1 校分）."""
    cfg = school.config
    return {
        "slug": cfg.slug,
        "name": cfg.name,
        "short": ref.short or cfg.short_name,
        "region": ref.region or cfg.region,
        "status": ref.status,
        "rooms": len(school.rooms),
        "lessons": len(school.lessons),
        "buildings": len(cfg.buildings),
        "periods": len(cfg.periods),
        "days": len(cfg.days),
        "terms": len(cfg.terms),
        "data_updated": cfg.data_updated,
        "source": cfg.source,
    }


def build_all(schools_dir: str | Path = "schools", out_dir: str | Path = "dist") -> list[str]:
    """レジストリ掲載の全校をビルドして dist/ へ書き出し、slug 一覧を返す."""
    schools_dir = Path(schools_dir)
    out_dir = Path(out_dir)
    (out_dir / "schools").mkdir(parents=True, exist_ok=True)

    refs = visible_schools(load_registry(schools_dir / "index.json"))
    built: list[str] = []
    stats: list[dict] = []
    index: list[dict] = []
    for ref in refs:
        school = LoadedSchool.load(ref.slug, base_dir=schools_dir)
        cfg = school.config
        payload = build_school_payload(school)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        (out_dir / "schools" / f"{ref.slug}.json").write_text(body, encoding="utf-8")
        built.append(ref.slug)
        stats.append(school_stats(school, ref))
        index.append({
            "slug": cfg.slug,
            "name": cfg.name,
            "short": ref.short or cfg.short_name,
            "region": ref.region or cfg.region,
            "status": ref.status,
            "data_updated": cfg.data_updated,
            "v": hashlib.sha1(body.encode("utf-8")).hexdigest()[:8],  # キャッシュバスティング用
        })

    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # ダッシュボード用の集計（静的統計）。稼働統計（予約・報告）は実行時に合算する。
    stats_doc = {
        "totals": {
            "schools": len(stats),
            "rooms": sum(s["rooms"] for s in stats),
            "lessons": sum(s["lessons"] for s in stats),
        },
        "schools": stats,
    }
    (out_dir / "stats.json").write_text(
        json.dumps(stats_doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return built


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schools", default="schools", type=Path)
    parser.add_argument("--out", default="dist", type=Path)
    args = parser.parse_args(argv)

    built = build_all(args.schools, args.out)
    for slug in built:
        size = (args.out / "schools" / f"{slug}.json").stat().st_size
        print(f"  {slug:14s} {size:>9,} bytes")
    print(f"ビルド完了: {len(built)} 校 → {args.out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
