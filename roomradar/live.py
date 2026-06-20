"""動的レイヤ：学校スコープ付きの仮予約・使用中報告ストア（DESIGN.md §5.4）.

スケール運用（ROADMAP フェーズ3）に向け、ストレージを **バックエンド抽象化** し、
``DATABASE_URL`` で SQLite / PostgreSQL を切り替えられる。すべての行に ``school``
列を持ち、インデックス先頭も ``school`` なので学校で水平分割しやすい。

失効時刻（``expires_at``）は **UTC の ISO 文字列** で保存する（学校ごとにタイムゾーンが
異なっても、文字列比較での失効判定が正しく働くようにするため）。

    # SQLite（既定）
    LiveStore("live.db")
    # PostgreSQL
    DATABASE_URL=postgresql://user:pass@host/db  → open_store()
"""

from __future__ import annotations

import datetime
import os
import secrets
import sqlite3
import string
from pathlib import Path

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def make_cancel_code(length: int = 6) -> str:
    """キャンセル用コード（英大文字＋数字）。``secrets`` で生成."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# バックエンド（接続・プレースホルダ・DDL の差分だけを持つ）
# ---------------------------------------------------------------------------
class Backend:
    """ストレージバックエンドの基底。SQL は LiveStore 側で共通化する."""

    paramstyle = "?"

    def connect(self):  # pragma: no cover - 抽象
        raise NotImplementedError

    def ddl(self) -> list[str]:  # pragma: no cover - 抽象
        raise NotImplementedError


class SqliteBackend(Backend):
    paramstyle = "?"

    def __init__(self, path: str | Path = "live.db") -> None:
        self.path = str(path)

    def connect(self):
        return sqlite3.connect(self.path)

    def ddl(self) -> list[str]:
        return [
            """CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school TEXT NOT NULL, room TEXT NOT NULL, building TEXT NOT NULL,
                day TEXT NOT NULL, period INTEGER NOT NULL,
                name TEXT NOT NULL, purpose TEXT,
                cancel_code TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_res ON reservations (school, day, period, room)",
            """CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school TEXT NOT NULL, room TEXT NOT NULL,
                day TEXT NOT NULL, period INTEGER NOT NULL,
                cancel_code TEXT NOT NULL, expires_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_rep ON reports (school, day, period, room)",
        ]


class PostgresBackend(Backend):
    """PostgreSQL バックエンド（``psycopg`` を遅延 import）.

    実運用向け。CI/既定では使用しないため、psycopg 未導入でも本モジュールは読み込める。
    """

    paramstyle = "%s"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def connect(self):
        import psycopg  # 遅延 import（未導入環境を壊さない）

        return psycopg.connect(self.dsn)

    def ddl(self) -> list[str]:
        return [
            """CREATE TABLE IF NOT EXISTS reservations (
                id BIGSERIAL PRIMARY KEY,
                school TEXT NOT NULL, room TEXT NOT NULL, building TEXT NOT NULL,
                day TEXT NOT NULL, period INTEGER NOT NULL,
                name TEXT NOT NULL, purpose TEXT,
                cancel_code TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_res ON reservations (school, day, period, room)",
            """CREATE TABLE IF NOT EXISTS reports (
                id BIGSERIAL PRIMARY KEY,
                school TEXT NOT NULL, room TEXT NOT NULL,
                day TEXT NOT NULL, period INTEGER NOT NULL,
                cancel_code TEXT NOT NULL, expires_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_rep ON reports (school, day, period, room)",
        ]


def select_backend(source: str | Path | None = None) -> Backend:
    """接続文字列から適切なバックエンドを選ぶ.

    - ``postgres://`` / ``postgresql://`` → PostgreSQL
    - ``sqlite:///path`` → SQLite（path）
    - その他の文字列 / Path → SQLite ファイルパス
    - ``None`` → 環境変数 ``DATABASE_URL``、無ければ ``live.db``
    """
    if source is None:
        source = os.environ.get("DATABASE_URL") or "live.db"
    text = str(source)
    if text.startswith(("postgres://", "postgresql://")):
        return PostgresBackend(text)
    if text.startswith("sqlite:///"):
        return SqliteBackend(text[len("sqlite:///"):])
    return SqliteBackend(text)


def open_store(url: str | None = None) -> "LiveStore":
    """``DATABASE_URL``（または引数）からバックエンドを選んで LiveStore を返す."""
    return LiveStore(select_backend(url))


# ---------------------------------------------------------------------------
# ストア本体（SQL はバックエンド非依存。プレースホルダだけ差し替える）
# ---------------------------------------------------------------------------
class LiveStore:
    """予約・報告の永続化。接続は呼び出しごとに開閉する."""

    def __init__(self, source: "Backend | str | Path" = "live.db") -> None:
        self.backend: Backend = source if isinstance(source, Backend) else select_backend(source)
        self._ensure_schema()

    # --- 低レベル実行 ------------------------------------------------------
    def _sql(self, sql: str) -> str:
        return sql if self.backend.paramstyle == "?" else sql.replace("?", self.backend.paramstyle)

    def _execute(self, sql: str, params: tuple = (), *, fetch: str | None = None):
        conn = self.backend.connect()
        try:
            cur = conn.cursor()
            cur.execute(self._sql(sql), params)
            result = cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
            conn.commit()
            return result
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        conn = self.backend.connect()
        try:
            cur = conn.cursor()
            for stmt in self.backend.ddl():
                cur.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    # --- 失効処理 ----------------------------------------------------------
    def cleanup(self, now: datetime.datetime | None = None) -> None:
        """expires_at（UTC）が now より前の予約・報告を削除する."""
        now_iso = now.astimezone(datetime.timezone.utc).isoformat() if now else _utcnow_iso()
        self._execute("DELETE FROM reservations WHERE expires_at < ?", (now_iso,))
        self._execute("DELETE FROM reports WHERE expires_at < ?", (now_iso,))

    # --- 予約 --------------------------------------------------------------
    def reserve(
        self,
        school: str,
        *,
        room: str,
        building: str,
        day: str,
        period: int,
        name: str,
        purpose: str,
        expires_at: str,
        created_at: str | None = None,
    ) -> tuple[str, int]:
        """予約を 1 件追加し、(cancel_code, その教室の予約数) を返す."""
        code = make_cancel_code()
        created = created_at or _utcnow_iso()
        self._execute(
            "INSERT INTO reservations "
            "(school, room, building, day, period, name, purpose, cancel_code, created_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (school, room, building, day, period, name, purpose, code, created, expires_at),
        )
        row = self._execute(
            "SELECT COUNT(*) FROM reservations WHERE school=? AND day=? AND period=? AND room=?",
            (school, day, period, room),
            fetch="one",
        )
        return code, int(row[0])

    def cancel_reservation(
        self, school: str, *, room: str, day: str, period: int, cancel_code: str
    ) -> bool:
        before = self._count("reservations", school, room, day, period, cancel_code)
        self._execute(
            "DELETE FROM reservations "
            "WHERE school=? AND room=? AND day=? AND period=? AND cancel_code=?",
            (school, room, day, period, cancel_code),
        )
        after = self._count("reservations", school, room, day, period, cancel_code)
        return after < before

    def list_reservations(self, school: str, *, day: str, period: int) -> list[dict]:
        rows = self._execute(
            "SELECT room, building, name, purpose FROM reservations "
            "WHERE school=? AND day=? AND period=? ORDER BY room",
            (school, day, period),
            fetch="all",
        )
        return [{"room": r[0], "building": r[1], "name": r[2], "purpose": r[3]} for r in rows]

    def reservation_counts(self, school: str, *, day: str, period: int) -> dict[str, int]:
        rows = self._execute(
            "SELECT room, COUNT(*) FROM reservations "
            "WHERE school=? AND day=? AND period=? GROUP BY room",
            (school, day, period),
            fetch="all",
        )
        return {r[0]: int(r[1]) for r in rows}

    # --- 使用中報告 --------------------------------------------------------
    def report(
        self, school: str, *, room: str, day: str, period: int, expires_at: str
    ) -> tuple[str, int]:
        code = make_cancel_code()
        self._execute(
            "INSERT INTO reports (school, room, day, period, cancel_code, expires_at) "
            "VALUES (?,?,?,?,?,?)",
            (school, room, day, period, code, expires_at),
        )
        row = self._execute(
            "SELECT COUNT(*) FROM reports WHERE school=? AND day=? AND period=? AND room=?",
            (school, day, period, room),
            fetch="one",
        )
        return code, int(row[0])

    def cancel_report(
        self, school: str, *, room: str, day: str, period: int, cancel_code: str
    ) -> bool:
        before = self._count("reports", school, room, day, period, cancel_code)
        self._execute(
            "DELETE FROM reports "
            "WHERE school=? AND room=? AND day=? AND period=? AND cancel_code=?",
            (school, room, day, period, cancel_code),
        )
        after = self._count("reports", school, room, day, period, cancel_code)
        return after < before

    def report_counts(self, school: str, *, day: str, period: int) -> dict[str, int]:
        rows = self._execute(
            "SELECT room, COUNT(*) FROM reports "
            "WHERE school=? AND day=? AND period=? GROUP BY room",
            (school, day, period),
            fetch="all",
        )
        return {r[0]: int(r[1]) for r in rows}

    # --- 横断集計（運用ダッシュボード用） ----------------------------------
    def totals(self) -> dict[str, int]:
        res = self._execute("SELECT COUNT(*) FROM reservations", fetch="one")[0]
        rep = self._execute("SELECT COUNT(*) FROM reports", fetch="one")[0]
        return {"reservations": int(res), "reports": int(rep)}

    def active_by_school(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}

        def bucket(slug: str) -> dict[str, int]:
            return out.setdefault(slug, {"reservations": 0, "reports": 0})

        for row in self._execute(
            "SELECT school, COUNT(*) FROM reservations GROUP BY school", fetch="all"
        ):
            bucket(row[0])["reservations"] = int(row[1])
        for row in self._execute(
            "SELECT school, COUNT(*) FROM reports GROUP BY school", fetch="all"
        ):
            bucket(row[0])["reports"] = int(row[1])
        return out

    # --- 内部 --------------------------------------------------------------
    def _count(self, table: str, school: str, room: str, day: str, period: int, code: str) -> int:
        row = self._execute(
            f"SELECT COUNT(*) FROM {table} "
            "WHERE school=? AND room=? AND day=? AND period=? AND cancel_code=?",
            (school, room, day, period, code),
            fetch="one",
        )
        return int(row[0])
