"""クロスチェック：web/availability.js（クライアント計算）の結果が
Python エンジンと一致するかを Node で実行して検証する.

Node が無い環境ではスキップする。
"""

import datetime
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from roomradar.school import LoadedSchool

REPO = Path(__file__).resolve().parent.parent
SCHOOLS = REPO / "schools"
NODE = shutil.which("node")

_spec = importlib.util.spec_from_file_location("build", REPO / "scripts" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

# 2026-06-19（前期）で固定して比較
PY_DATE = datetime.date(2026, 6, 19)
JS_DATE = "new Date(2026, 5, 19)"  # JS は月が 0 始まり

_NODE_TEMPLATE = """
const path = require("path");
const RR = require(path.resolve(%(js)s));
const data = require(path.resolve(%(json)s));
const today = %(date)s;
const out = {};
for (const day of data.days) {
  for (const p of data.periods) {
    out[day + "/" + p.period] =
      RR.freeRooms(data, { day: day, period: p.period, today: today }).map((r) => r.room);
  }
}
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "node が見つからないためスキップ")
class ClientJsCrossCheck(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        build.build_all(SCHOOLS, self.out)

    def tearDown(self):
        self._tmp.cleanup()

    def _js_free(self, slug: str) -> dict:
        js = json.dumps(str((REPO / "web" / "availability.js")))
        jsonpath = json.dumps(str(self.out / "schools" / f"{slug}.json"))
        src = _NODE_TEMPLATE % {"js": js, "json": jsonpath, "date": JS_DATE}
        res = subprocess.run([NODE, "-e", src], capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, msg=res.stderr)
        return json.loads(res.stdout)

    def _engine_free(self, slug: str) -> dict:
        school = LoadedSchool.load(slug, base_dir=SCHOOLS)
        out = {}
        for day in school.config.days:
            for period in school.config.period_numbers:
                rooms = [r.room for r in school.free_rooms(day, period, today=PY_DATE)]
                out[f"{day}/{period}"] = rooms
        return out

    def test_nust_js_matches_engine(self):
        self.assertEqual(self._js_free("nust"), self._engine_free("nust"))

    def test_example_js_matches_engine(self):
        self.assertEqual(self._js_free("example-tech"), self._engine_free("example-tech"))


if __name__ == "__main__":
    unittest.main()
