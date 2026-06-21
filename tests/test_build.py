"""build.py が出力する配信用 JSON が、エンジンと同じ空き判定を再現できるか検証."""

import datetime
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from roomradar.school import LoadedSchool

REPO = Path(__file__).resolve().parent.parent
SCHOOLS = REPO / "schools"

# scripts/build.py を import
_spec = importlib.util.spec_from_file_location("build", REPO / "scripts" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def free_from_payload(payload: dict, day: str, period: int, active: list[str]) -> list[str]:
    """配信用 JSON だけから空き教室名を計算（クライアント計算の Python 等価実装）."""
    occ = set()
    for term, days in payload["occupied"].items():
        if term in active:
            occ |= set(days.get(day, {}).get(str(period), []))
    order = {b["name"]: i for i, b in enumerate(payload["buildings"])}
    fb = len(order)
    cand = [r for r in payload["rooms"] if r["room"] not in occ]
    cand.sort(key=lambda r: (order.get(r["building"], fb), r["room"]))
    return [r["room"] for r in cand]


class BuildTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        build.build_all(SCHOOLS, self.out)

    def tearDown(self):
        self._tmp.cleanup()

    def _payload(self, slug):
        return json.loads((self.out / "schools" / f"{slug}.json").read_text(encoding="utf-8"))

    def test_index_written(self):
        idx = json.loads((self.out / "index.json").read_text(encoding="utf-8"))
        self.assertEqual({s["slug"] for s in idx}, {"nust", "example-tech"})

    def test_index_has_version_and_freshness(self):
        idx = json.loads((self.out / "index.json").read_text(encoding="utf-8"))
        for e in idx:
            self.assertTrue(e["v"])  # キャッシュバスティング用ハッシュ
            self.assertIn("data_updated", e)
        nust = next(e for e in idx if e["slug"] == "nust")
        self.assertEqual(nust["data_updated"], "2026-04-01")

    def test_stats_written(self):
        stats = json.loads((self.out / "stats.json").read_text(encoding="utf-8"))
        self.assertEqual(stats["totals"]["schools"], 2)
        nust = next(s for s in stats["schools"] if s["slug"] == "nust")
        self.assertEqual(nust["rooms"], 181)
        self.assertEqual(nust["buildings"], 3)
        # 全校合計の教室数は各校の合計と一致
        self.assertEqual(stats["totals"]["rooms"], sum(s["rooms"] for s in stats["schools"]))

    def test_payload_matches_engine_nust(self):
        school = LoadedSchool.load("nust", base_dir=SCHOOLS)
        payload = self._payload("nust")
        active = ["前期", "通年"]
        for day in school.config.days:
            for period in school.config.period_numbers:
                want = [r.room for r in school.free_rooms_with_terms(day, period, active_terms=active)]
                got = free_from_payload(payload, day, period, active)
                self.assertEqual(got, want, msg=f"nust {day}{period}限")

    def test_payload_matches_engine_example(self):
        school = LoadedSchool.load("example-tech", base_dir=SCHOOLS)
        payload = self._payload("example-tech")
        for active in (["前期"], ["後期"]):
            for day in school.config.days:
                for period in school.config.period_numbers:
                    want = [r.room for r in school.free_rooms_with_terms(day, period, active_terms=active)]
                    got = free_from_payload(payload, day, period, active)
                    self.assertEqual(got, want, msg=f"example-tech {active} {day}{period}限")


if __name__ == "__main__":
    unittest.main()
