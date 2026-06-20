"""LiveStore（学校スコープ付き 予約・報告）の単体テスト."""

import datetime
import tempfile
import unittest
from pathlib import Path

from roomradar.live import LiveStore, make_cancel_code

FUTURE = "2999-01-01T00:00:00+00:00"
PAST = "2000-01-01T00:00:00+00:00"


class LiveStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LiveStore(Path(self._tmp.name) / "live.db")

    def tearDown(self):
        self._tmp.cleanup()

    def _reserve(self, school, room="101", expires=FUTURE):
        return self.store.reserve(
            school, room=room, building="本館", day="月", period=1,
            name="匿名", purpose="自習", expires_at=expires,
        )

    def test_reserve_counts(self):
        _, count = self._reserve("nust")
        self.assertEqual(count, 1)
        self.assertEqual(self.store.reservation_counts("nust", day="月", period=1), {"101": 1})

    def test_school_isolation(self):
        self._reserve("nust", room="101")
        self._reserve("example-tech", room="101")
        # 同じ room/day/period でも学校ごとに独立
        self.assertEqual(self.store.reservation_counts("nust", day="月", period=1), {"101": 1})
        self.assertEqual(
            self.store.reservation_counts("example-tech", day="月", period=1), {"101": 1}
        )

    def test_cancel_requires_matching_code(self):
        code, _ = self._reserve("nust")
        self.assertFalse(
            self.store.cancel_reservation("nust", room="101", day="月", period=1, cancel_code="ZZZZZZ")
        )
        # 他校から同じコードでも消えない
        self.assertFalse(
            self.store.cancel_reservation("other", room="101", day="月", period=1, cancel_code=code)
        )
        self.assertTrue(
            self.store.cancel_reservation("nust", room="101", day="月", period=1, cancel_code=code)
        )
        self.assertEqual(self.store.reservation_counts("nust", day="月", period=1), {})

    def test_cleanup_removes_expired_only(self):
        self._reserve("nust", room="101", expires=PAST)
        self._reserve("nust", room="102", expires=FUTURE)
        self.store.report("nust", room="201", day="月", period=1, expires_at=PAST)
        self.store.cleanup(datetime.datetime(2026, 6, 19, tzinfo=datetime.timezone.utc))
        self.assertEqual(self.store.reservation_counts("nust", day="月", period=1), {"102": 1})
        self.assertEqual(self.store.report_counts("nust", day="月", period=1), {})

    def test_reports(self):
        _, c1 = self.store.report("nust", room="101", day="火", period=2, expires_at=FUTURE)
        _, c2 = self.store.report("nust", room="101", day="火", period=2, expires_at=FUTURE)
        self.assertEqual((c1, c2), (1, 2))
        self.assertEqual(self.store.report_counts("nust", day="火", period=2), {"101": 2})

    def test_list_reservations(self):
        self._reserve("nust", room="101")
        rows = self.store.list_reservations("nust", day="月", period=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["room"], "101")
        self.assertEqual(rows[0]["building"], "本館")

    def test_cancel_code_format(self):
        code = make_cancel_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isalnum())

    def test_cross_school_aggregates(self):
        self._reserve("nust", room="101")
        self._reserve("nust", room="102")
        self._reserve("example-tech", room="201")
        self.store.report("nust", room="101", day="月", period=1, expires_at=FUTURE)
        self.assertEqual(self.store.totals(), {"reservations": 3, "reports": 1})
        by = self.store.active_by_school()
        self.assertEqual(by["nust"], {"reservations": 2, "reports": 1})
        self.assertEqual(by["example-tech"], {"reservations": 1, "reports": 0})


if __name__ == "__main__":
    unittest.main()
