"""terms.active_terms / in_season の単体テスト."""

import datetime
import unittest

from roomradar.config import Term
from roomradar.terms import active_terms, in_season

NUST_TERMS = [
    Term(id="前期", start="04-01", end="09-20"),
    Term(id="後期", start="09-21", end="03-31"),
    Term(id="通年", always=True),
]


class InSeasonTest(unittest.TestCase):
    def test_normal_range(self):
        self.assertTrue(in_season((6, 19), (4, 1), (9, 20)))
        self.assertFalse(in_season((10, 1), (4, 1), (9, 20)))

    def test_boundaries_inclusive(self):
        self.assertTrue(in_season((4, 1), (4, 1), (9, 20)))
        self.assertTrue(in_season((9, 20), (4, 1), (9, 20)))

    def test_year_wrap(self):
        # 後期: 09-21 〜 03-31（年末跨ぎ）
        self.assertTrue(in_season((12, 1), (9, 21), (3, 31)))
        self.assertTrue(in_season((1, 15), (9, 21), (3, 31)))
        self.assertFalse(in_season((6, 1), (9, 21), (3, 31)))


class ActiveTermsTest(unittest.TestCase):
    def test_first_semester(self):
        self.assertEqual(active_terms(NUST_TERMS, datetime.date(2026, 6, 19)), ["前期", "通年"])

    def test_second_semester_autumn(self):
        self.assertEqual(active_terms(NUST_TERMS, datetime.date(2026, 12, 1)), ["後期", "通年"])

    def test_second_semester_winter_wrap(self):
        self.assertEqual(active_terms(NUST_TERMS, datetime.date(2026, 1, 15)), ["後期", "通年"])

    def test_boundary_switch(self):
        self.assertEqual(active_terms(NUST_TERMS, datetime.date(2026, 9, 20)), ["前期", "通年"])
        self.assertEqual(active_terms(NUST_TERMS, datetime.date(2026, 9, 21)), ["後期", "通年"])

    def test_always_only(self):
        self.assertEqual(active_terms([Term(id="通年", always=True)], datetime.date(2026, 1, 1)), ["通年"])


if __name__ == "__main__":
    unittest.main()
