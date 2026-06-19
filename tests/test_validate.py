"""scripts/validate.py のテスト（正常データは通り、壊れたデータは検出する）."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHOOLS = REPO / "schools"

_spec = importlib.util.spec_from_file_location("validate", REPO / "scripts" / "validate.py")
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

BROKEN_CONFIG = """
slug: broken
name: 壊れた学校
short_name: 壊れ
days: [月]
periods:
  - { period: 1, start: "09:00", end: "10:30" }
terms:
  - { id: 前期, start: "04-01", end: "09-20" }
buildings:
  - { id: main, name: 本館, color: "#fff" }
"""

BROKEN_SCHEDULE = """department,term,day,period,room,building,course
情報,前期,月,1,101,本館,A
情報,前期,月,1,102,実習棟,B
情報,前期,月,9,103,本館,C
情報,前期,火,1,104,本館,D
情報,前期,月,1,101,本館,A
"""


class ValidateRealSchoolsTest(unittest.TestCase):
    def test_registered_schools_pass(self):
        for slug in ("nust", "example-tech"):
            errors, _ = validate.validate_school(slug, SCHOOLS)
            self.assertEqual(errors, [], msg=f"{slug}: {errors}")


class ValidateBrokenSchoolTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name) / "broken"
        d.mkdir()
        (d / "config.yml").write_text(BROKEN_CONFIG, encoding="utf-8")
        (d / "schedule.csv").write_text(BROKEN_SCHEDULE, encoding="utf-8")
        self.base = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_detects_errors_and_warnings(self):
        errors, warnings = validate.validate_school("broken", self.base)
        joined = "\n".join(errors)
        self.assertIn("実習棟", joined)  # 建物名の不一致
        self.assertTrue(any("period '9'" in e for e in errors))  # 時限外
        self.assertTrue(any("day '火'" in e for e in errors))  # 曜日外
        self.assertTrue(any("重複" in w for w in warnings))  # 重複行の警告

    def test_missing_schedule_is_error(self):
        d = self.base / "noschedule"
        d.mkdir()
        (d / "config.yml").write_text(BROKEN_CONFIG, encoding="utf-8")
        errors, _ = validate.validate_school("noschedule", self.base)
        self.assertTrue(any("schedule.csv" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
