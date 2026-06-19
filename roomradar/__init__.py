"""RoomRadar — 全国対応マルチテナント空き教室検索のコアエンジン.

学校固有情報（校舎・時限・学期・曜日・色・学校名）はすべて
``schools/<slug>/config.yml`` と CSV データへ外部化されており、
このパッケージのコードは **学校に依存しない**。

主要モジュール:
    config        学校設定 (config.yml) / レジストリ (index.json) のローダ
    terms         日付から有効な学期を求める純粋関数
    availability  時間割と教室から空き教室を求める純粋関数（空き判定エンジン）
    data          schedule.csv / classrooms.csv のローダ
    school        設定＋データを束ねた 1 校分のロード済みモデル
"""

from .config import (
    Building,
    Period,
    SchoolConfig,
    SchoolRef,
    Term,
    load_registry,
    load_school_config,
)
from .availability import Lesson, Room, free_rooms
from .terms import active_terms
from .school import LoadedSchool

__all__ = [
    "Building",
    "Period",
    "Term",
    "SchoolConfig",
    "SchoolRef",
    "load_school_config",
    "load_registry",
    "Lesson",
    "Room",
    "free_rooms",
    "active_terms",
    "LoadedSchool",
]

__version__ = "0.1.0"
