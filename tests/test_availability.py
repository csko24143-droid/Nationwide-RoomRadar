"""availability.free_rooms / occupied_rooms の単体テスト（学校非依存ロジック）."""

import unittest

from roomradar.availability import Lesson, Room, free_rooms, occupied_rooms

ROOMS = [
    Room(room="101", building="本館"),
    Room(room="102", building="本館"),
    Room(room="201", building="本館"),
    Room(room="L1", building="実習棟"),
    Room(room="L2", building="実習棟"),
]
LESSONS = [
    Lesson(term="前期", day="月", period=1, room="101", building="本館"),
    Lesson(term="前期", day="月", period=1, room="L1", building="実習棟"),
    Lesson(term="後期", day="月", period=1, room="102", building="本館"),  # 別学期
    Lesson(term="前期", day="火", period=1, room="201", building="本館"),  # 別曜日
]
ORDER = ["本館", "実習棟"]


class OccupiedTest(unittest.TestCase):
    def test_filters_by_day_period_and_term(self):
        occ = occupied_rooms(LESSONS, day="月", period=1, active_terms=["前期"])
        self.assertEqual(occ, {"101", "L1"})

    def test_inactive_term_not_counted(self):
        # 後期の 102 は前期検索では使用中にならない
        occ = occupied_rooms(LESSONS, day="月", period=1, active_terms=["前期"])
        self.assertNotIn("102", occ)


class FreeRoomsTest(unittest.TestCase):
    def test_difference_and_sort(self):
        free = free_rooms(
            LESSONS, ROOMS, day="月", period=1, active_terms=["前期"], building_order=ORDER
        )
        # 使用中: 101, L1 → 空き: 102,201(本館) / L2(実習棟)、校舎順→室名順
        self.assertEqual([r.room for r in free], ["102", "201", "L2"])

    def test_building_filter(self):
        free = free_rooms(
            LESSONS,
            ROOMS,
            day="月",
            period=1,
            active_terms=["前期"],
            building_order=ORDER,
            building="実習棟",
        )
        self.assertEqual([r.room for r in free], ["L2"])

    def test_active_term_changes_result(self):
        # 後期では 102 が使用中、101 は空き
        free = free_rooms(
            LESSONS, ROOMS, day="月", period=1, active_terms=["後期"], building_order=ORDER
        )
        rooms = {r.room for r in free}
        self.assertIn("101", rooms)
        self.assertNotIn("102", rooms)

    def test_unknown_building_sorts_last(self):
        rooms = ROOMS + [Room(room="X1", building="未登録棟")]
        # 何も使用中でない時間（水4限）→ 全室が空き。config 未登録の校舎は末尾へ。
        free = free_rooms(
            LESSONS, rooms, day="水", period=4, active_terms=["前期"], building_order=ORDER
        )
        self.assertEqual(len(free), len(rooms))
        self.assertEqual(free[-1].room, "X1")


if __name__ == "__main__":
    unittest.main()
