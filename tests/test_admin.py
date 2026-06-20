"""管理UI（/admin）の結合テスト。ADMIN_TOKEN 保護・編集・保存前検証を確認."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
TOKEN = "secret123"

try:
    import flask  # noqa: F401
    HAS_FLASK = True
except Exception:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, "Flask 未導入のためスキップ")
class AdminTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.schools = base / "schools"
        shutil.copytree(REPO / "schools", self.schools)
        from roomradar.webapp import create_app

        self.app = create_app(self.schools, live_db=str(base / "live.db"))
        self.c = self.app.test_client()

    def tearDown(self):
        self._tmp.cleanup()

    def _config_text(self) -> str:
        return (self.schools / "example-tech" / "config.yml").read_text(encoding="utf-8")

    def test_disabled_without_token_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.c.get("/admin").status_code, 404)

    def test_forbidden_with_wrong_token(self):
        with mock.patch.dict(os.environ, {"ADMIN_TOKEN": TOKEN}):
            self.assertEqual(self.c.get("/admin").status_code, 403)
            self.assertEqual(self.c.get("/admin?token=wrong").status_code, 403)

    def test_home_and_edit_view(self):
        with mock.patch.dict(os.environ, {"ADMIN_TOKEN": TOKEN}):
            r = self.c.get(f"/admin?token={TOKEN}")
            self.assertEqual(r.status_code, 200)
            self.assertIn("管理コンソール", r.get_data(as_text=True))
            r = self.c.get(f"/admin/example-tech?token={TOKEN}")
            self.assertIn("slug: example-tech", r.get_data(as_text=True))

    def test_save_valid_config_updates_file_and_cache(self):
        with mock.patch.dict(os.environ, {"ADMIN_TOKEN": TOKEN}):
            new = self._config_text().replace("short_name: サンプル工科", "short_name: 改名テスト")
            r = self.c.post("/admin/example-tech/config", data={"token": TOKEN, "content": new})
            self.assertEqual(r.status_code, 200)
            self.assertIn("保存しました", r.get_data(as_text=True))
            self.assertIn("改名テスト", self._config_text())
            # キャッシュ破棄 → 学校ページに即反映
            self.assertIn("改名テスト", self.c.get("/s/example-tech").get_data(as_text=True))

    def test_save_invalid_yaml_rejected(self):
        with mock.patch.dict(os.environ, {"ADMIN_TOKEN": TOKEN}):
            before = self._config_text()
            r = self.c.post(
                "/admin/example-tech/config", data={"token": TOKEN, "content": "name: [unclosed\n"}
            )
            self.assertEqual(r.status_code, 200)
            self.assertIn("保存しませんでした", r.get_data(as_text=True))
            self.assertEqual(self._config_text(), before)  # ファイルは不変

    def test_slug_change_rejected(self):
        with mock.patch.dict(os.environ, {"ADMIN_TOKEN": TOKEN}):
            changed = self._config_text().replace("slug: example-tech", "slug: hacked")
            r = self.c.post("/admin/example-tech/config", data={"token": TOKEN, "content": changed})
            self.assertIn("slug は", r.get_data(as_text=True))
            self.assertIn("slug: example-tech", self._config_text())

    def test_path_traversal_blocked(self):
        with mock.patch.dict(os.environ, {"ADMIN_TOKEN": TOKEN}):
            self.assertEqual(self.c.get(f"/admin/..%2f..%2fetc?token={TOKEN}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
