"""運用ダッシュボード（/dashboard・/api/stats）の結合テスト."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("build", REPO / "scripts" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

try:
    import flask  # noqa: F401
    HAS_FLASK = True
except Exception:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, "Flask 未導入のためスキップ")
class DashboardTest(unittest.TestCase):
    def setUp(self):
        # ダッシュボードは repo_root/dist/stats.json を読むため、ビルドしておく
        build.build_all(REPO / "schools", REPO / "dist")
        from roomradar.webapp import create_app

        self.app = create_app("schools", live_db=tempfile.mktemp(suffix=".db"))
        self.c = self.app.test_client()

    def test_api_stats_shape(self):
        doc = self.c.get("/api/stats").get_json()
        self.assertEqual(doc["totals"]["schools"], 2)
        self.assertIn("reservations", doc["totals"])
        nust = next(s for s in doc["schools"] if s["slug"] == "nust")
        self.assertEqual(nust["rooms"], 181)

    def test_dashboard_reflects_live_reservation(self):
        # example-tech 火3限の空き室 201 を予約 → ダッシュボードに反映
        r = self.c.post(
            "/api/example-tech/reserve",
            json={"room": "201", "building": "本館", "day": "火", "period": 3, "name": "テスト"},
        ).get_json()
        self.assertTrue(r["ok"])
        doc = self.c.get("/api/stats").get_json()
        self.assertEqual(doc["totals"]["reservations"], 1)
        ex = next(s for s in doc["schools"] if s["slug"] == "example-tech")
        self.assertEqual(ex["reservations"], 1)

        html = self.c.get("/dashboard").get_data(as_text=True)
        self.assertIn("運用ダッシュボード", html)
        self.assertIn("日本大学 理工学部", html)
        self.assertIn("サンプル工科大学", html)
        self.assertIn("鮮度", html)  # フェーズ4: データ鮮度列

    def test_home_groups_by_region(self):
        home = self.c.get("/").get_data(as_text=True)
        self.assertIn("東京・千葉", home)
        self.assertIn("add-school.html", home)  # フォーム導線

    def test_school_page_shows_freshness(self):
        page = self.c.get("/s/nust").get_data(as_text=True)
        self.assertIn("データ最終更新: 2026-04-01", page)

    def test_dist_cache_headers(self):
        self.assertIn("max-age=86400", self.c.get("/dist/schools/nust.json").headers.get("Cache-Control", ""))
        self.assertIn("max-age=300", self.c.get("/dist/index.json").headers.get("Cache-Control", ""))

    def test_add_school_form_served(self):
        r = self.c.get("/app/add-school.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("追加リクエスト", r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
