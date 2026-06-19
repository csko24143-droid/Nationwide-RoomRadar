"""動的レイヤ：学校スコープ付きの仮予約・使用中報告ストア（DESIGN.md §5.4）.

旧 ``nust-room-search`` の reservations / reports を、すべての行へ ``school`` 列を
付与した複合キーへ拡張したもの。1 つの SQLite ファイルに 2 テーブルを持ち、
学校間でデータが衝突しないようにする（インデックス先頭も ``school``）。

空き判定（静的コア）とは独立した「状態を持つ最小限のバックエンド」であり、
時限終了で自動失効する揮発データを扱う。
"""

from __future__ import annotations

import datetime
import secrets
import sqlite3
import string
from dataclasses import dataclass
from pathlib import Path

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def make_cancel_code(length: int = 6) -> str:
    """キャンセル用コード（英大文字＋数字）。``secrets`` で生成."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


@dataclass
class LiveStore:
    """予約・報告の永続化（SQLite）。接続は呼び出しごとに開閉する."""

    db_path: str | Path = "live.db"

    def __post_init__(self) -> None:
        self.db_path = str(self.db_path)
        self._ensure_schema()

    # --- 接続・スキーマ ----------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reservations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    school      TEXT NOT NULL,
                    room        TEXT NOT NULL,
                    building    TEXT NOT NULL,
                    day         TEXT NOT NULL,
                    period      INTEGER NOT NULL,
                    name        TEXT NOT NULL,
                    purpose     TEXT,
                    cancel_code TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    expires_at  TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_res ON reservations (school, day, period, room)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    school      TEXT NOT NULL,
                    room        TEXT NOT NULL,
                    day         TEXT NOT NULL,
                    period      INTEGER NOT NULL,
                    cancel_code TEXT NOT NULL,
                    expires_at  TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rep ON reports (school, day, period, room)"
            )

    # --- 失効処理 ----------------------------------------------------------
    def cleanup(self, now: datetime.datetime | None = None) -> None:
        """時限終了済み（expires_at < now）の予約・報告を削除する."""
        now_iso = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM reservations WHERE expires_at < ?", (now_iso,))
            conn.execute("DELETE FROM reports WHERE expires_at < ?", (now_iso,))

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
        created = created_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reservations "
                "(school, room, building, day, period, name, purpose, cancel_code, created_at, expires_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (school, room, building, day, period, name, purpose, code, created, expires_at),
            )
            count = conn.execute(
                "SELECT COUNT(*) FROM reservations WHERE school=? AND day=? AND period=? AND room=?",
                (school, day, period, room),
            ).fetchone()[0]
        return code, count

    def cancel_reservation(
        self, school: str, *, room: str, day: str, period: int, cancel_code: str
    ) -> bool:
        """キャンセルコードが一致する予約を削除する。削除できたら True."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM reservations "
                "WHERE school=? AND room=? AND day=? AND period=? AND cancel_code=?",
                (school, room, day, period, cancel_code),
            )
            return cur.rowcount > 0

    def list_reservations(self, school: str, *, day: str, period: int) -> list[dict]:
        """指定 学校×曜日×時限 の予約一覧."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT room, building, name, purpose FROM reservations "
                "WHERE school=? AND day=? AND period=? ORDER BY room",
                (school, day, period),
            ).fetchall()
        return [dict(r) for r in rows]

    def reservation_counts(self, school: str, *, day: str, period: int) -> dict[str, int]:
        """指定 学校×曜日×時限 の教室別予約数 {room: count}."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT room, COUNT(*) AS c FROM reservations "
                "WHERE school=? AND day=? AND period=? GROUP BY room",
                (school, day, period),
            ).fetchall()
        return {r["room"]: r["c"] for r in rows}

    # --- 使用中報告 --------------------------------------------------------
    def report(
        self, school: str, *, room: str, day: str, period: int, expires_at: str
    ) -> tuple[str, int]:
        """使用中報告を 1 件追加し、(cancel_code, その教室の報告数) を返す."""
        code = make_cancel_code()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reports (school, room, day, period, cancel_code, expires_at) "
                "VALUES (?,?,?,?,?,?)",
                (school, room, day, period, code, expires_at),
            )
            count = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE school=? AND day=? AND period=? AND room=?",
                (school, day, period, room),
            ).fetchone()[0]
        return code, count

    def cancel_report(
        self, school: str, *, room: str, day: str, period: int, cancel_code: str
    ) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM reports "
                "WHERE school=? AND room=? AND day=? AND period=? AND cancel_code=?",
                (school, room, day, period, cancel_code),
            )
            return cur.rowcount > 0

    def report_counts(self, school: str, *, day: str, period: int) -> dict[str, int]:
        """指定 学校×曜日×時限 の教室別報告数 {room: count}."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT room, COUNT(*) AS c FROM reports "
                "WHERE school=? AND day=? AND period=? GROUP BY room",
                (school, day, period),
            ).fetchall()
        return {r["room"]: r["c"] for r in rows}
