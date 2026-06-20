#!/usr/bin/env python3
"""学校データの検証 CLI（取り込み時の自動チェック）.

検証ロジック本体は :mod:`roomradar.validation`（CLI と管理UI で共用）。

    python scripts/validate.py            # レジストリ掲載の全校を検証
    python scripts/validate.py --slug nust
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roomradar.config import load_registry  # noqa: E402
from roomradar.validation import validate_school  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schools", default="schools", type=Path)
    parser.add_argument("--slug", help="特定の学校だけ検証（省略時はレジストリ全校）")
    args = parser.parse_args(argv)

    if args.slug:
        slugs = [args.slug]
    else:
        slugs = [r.slug for r in load_registry(args.schools / "index.json")]

    total_errors = 0
    for slug in slugs:
        errors, warnings = validate_school(slug, args.schools)
        total_errors += len(errors)
        status = "NG" if errors else "OK"
        print(f"[{status}] {slug}  (errors={len(errors)}, warnings={len(warnings)})")
        shown = warnings[:15]
        for w in shown:
            print(f"    ⚠ {w}")
        if len(warnings) > len(shown):
            print(f"    ⚠ …他 {len(warnings) - len(shown)} 件の警告")
        for e in errors[:50]:
            print(f"    ✗ {e}")

    if total_errors:
        print(f"\n検証失敗: {total_errors} 件のエラー", file=sys.stderr)
        return 1
    print("\n検証OK: すべての学校データが規定どおりです")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
