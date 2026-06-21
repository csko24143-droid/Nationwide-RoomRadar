"""設定/レジストリのローダと LoadedSchool の結合テスト（実データを使用）."""

import datetime
import tempfile
import unittest
from pathlib import Path

from roomradar.config import ConfigError, load_registry, load_school_config
from roomradar.school import LoadedSchool

SCHOOLS = Path(__file__).resolve().parent.parent / "schools"


class RegistryTest(unittest.TestCase):
    def test_load_registry(self):
        refs = load_registry(SCHOOLS / "index.json")
        slugs = {r.slug for r in refs}
        self.assertIn("nust", slugs)
        self.assertIn("example-tech", slugs)


class SchoolConfigTest(unittest.TestCase):
    def test_load_nust(self):
        cfg = load_school_config(SCHOOLS / "nust" / "config.yml")
        self.assertEqual(cfg.slug, "nust")
        self.assertEqual(len(cfg.periods), 6)
        self.assertEqual(cfg.building_names, ["タワースコラ", "駿河台校舎", "船橋校舎"])
        self.assertIn("土", cfg.days)
        # period キーが正しく読めている（YAML の no→false 問題の回帰防止）
        self.assertEqual(cfg.period_numbers, [1, 2, 3, 4, 5, 6])
        # データ鮮度メタ（フェーズ4）
        self.assertEqual(cfg.data_updated, "2026-04-01")
        self.assertTrue(cfg.source)

    def test_missing_required_field_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.yml"
            p.write_text("name: x\n", encoding="utf-8")  # slug 欠落
            with self.assertRaises(ConfigError):
                load_school_config(p)


class MultiTenantTest(unittest.TestCase):
    """同じコードが、構成の異なる 2 校をデータだけで扱えることを確認."""

    def test_two_schools_have_different_shape(self):
        nust = LoadedSchool.load("nust", base_dir=SCHOOLS)
        ex = LoadedSchool.load("example-tech", base_dir=SCHOOLS)
        self.assertEqual(len(nust.config.periods), 6)
        self.assertEqual(len(ex.config.periods), 4)
        self.assertNotEqual(nust.config.building_names, ex.config.building_names)

    def test_example_tech_known_result(self):
        ex = LoadedSchool.load("example-tech", base_dir=SCHOOLS)
        # 前期の月1限: 101(本館), L1(実習棟) が使用中 → 空きは 102,201,L2
        free = ex.free_rooms("月", 1, today=datetime.date(2026, 6, 19))
        self.assertEqual([r.room for r in free], ["102", "201", "L2"])

    def test_nust_loads_real_data(self):
        nust = LoadedSchool.load("nust", base_dir=SCHOOLS)
        self.assertEqual(len(nust.rooms), 181)
        self.assertGreater(len(nust.lessons), 10000)
        free = nust.free_rooms("月", 2, today=datetime.date(2026, 6, 19))
        # 空き室は母集合（181室）の部分集合で、重複なし
        self.assertLessEqual(len(free), 181)
        names = [r.room for r in free]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
