"""学校設定 (``config.yml``) と学校レジストリ (``index.json``) のローダ.

設計書 DESIGN.md §5.1 / §5.2 に対応する。ここで読み込んだ ``SchoolConfig`` が
時限・学期・校舎・曜日・色・学校名の **単一ソース** になり、サーバ／クライアント
双方へ供給される（DESIGN §8-3 の「時刻の単一ソース化」）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml


class ConfigError(ValueError):
    """設定ファイルの内容が不正なときに送出する."""


@dataclass(frozen=True)
class Period:
    """時限 1 コマ。``number`` は整数、``start``/``end`` は ``"HH:MM"``.

    YAML キーは ``period``（``no`` は YAML 1.1 でブール値 ``False`` と解釈されるため
    使わない）。
    """

    number: int
    start: str
    end: str


@dataclass(frozen=True)
class Term:
    """学期。``always=True`` は通年（常に有効）。``start``/``end`` は ``"MM-DD"``."""

    id: str
    start: str | None = None
    end: str | None = None
    always: bool = False


@dataclass(frozen=True)
class Building:
    """校舎。``name`` は時間割 CSV の ``building`` と完全一致させる（DESIGN §5.3）."""

    id: str
    name: str
    color: str = "#888888"


@dataclass(frozen=True)
class SchoolConfig:
    """1 校分の設定。``schools/<slug>/config.yml`` を読み込んだもの."""

    slug: str
    name: str
    short_name: str
    region: str = ""
    timezone: str = "Asia/Tokyo"
    accent: str = "#6c8fff"
    days: tuple[str, ...] = ()
    periods: tuple[Period, ...] = ()
    terms: tuple[Term, ...] = ()
    buildings: tuple[Building, ...] = ()
    ga4: str = ""
    disclaimer: str = ""

    # --- 便利アクセサ ------------------------------------------------------
    @property
    def building_names(self) -> list[str]:
        """config に並んだ順の校舎名一覧（空き一覧の表示順にも使う）."""
        return [b.name for b in self.buildings]

    @property
    def period_numbers(self) -> list[int]:
        return [p.number for p in self.periods]

    def period(self, number: int) -> Period | None:
        for p in self.periods:
            if p.number == number:
                return p
        return None


@dataclass(frozen=True)
class SchoolRef:
    """全国レジストリ（``schools/index.json``）の 1 エントリ."""

    slug: str
    name: str
    short: str = ""
    region: str = ""
    status: str = "active"  # active / beta / hidden


# ---------------------------------------------------------------------------
# ローダ
# ---------------------------------------------------------------------------
def load_school_config(path: str | Path) -> SchoolConfig:
    """``config.yml`` を読み込んで検証済みの :class:`SchoolConfig` を返す."""
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        return parse_school_config(fh.read(), source=str(path))


def parse_school_config(text: str, source: str = "<config>") -> SchoolConfig:
    """YAML テキストから検証済みの :class:`SchoolConfig` を作る（ファイルに書かずに検証）.

    管理UI（``/admin``）で、保存前に内容を検証するために使う。
    """
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{source}: YAML として解釈できません: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: トップレベルはマッピングである必要があります")

    path = source

    def require(key: str):
        if not raw.get(key):
            raise ConfigError(f"{path}: 必須項目 '{key}' がありません")
        return raw[key]

    slug = str(require("slug"))
    name = str(require("name"))
    short_name = str(raw.get("short_name") or name)

    theme = raw.get("theme") or {}
    accent = str(theme.get("accent") or "#6c8fff")

    days = tuple(str(d) for d in (raw.get("days") or []))

    periods = tuple(
        Period(number=int(p["period"]), start=str(p["start"]), end=str(p["end"]))
        for p in (raw.get("periods") or [])
    )
    terms = tuple(
        Term(
            id=str(t["id"]),
            start=(str(t["start"]) if t.get("start") else None),
            end=(str(t["end"]) if t.get("end") else None),
            always=bool(t.get("always", False)),
        )
        for t in (raw.get("terms") or [])
    )
    buildings = tuple(
        Building(id=str(b["id"]), name=str(b["name"]), color=str(b.get("color", "#888888")))
        for b in (raw.get("buildings") or [])
    )

    analytics = raw.get("analytics") or {}
    cfg = SchoolConfig(
        slug=slug,
        name=name,
        short_name=short_name,
        region=str(raw.get("region", "")),
        timezone=str(raw.get("timezone", "Asia/Tokyo")),
        accent=accent,
        days=days,
        periods=periods,
        terms=terms,
        buildings=buildings,
        ga4=str(analytics.get("ga4", "")),
        disclaimer=str(raw.get("disclaimer", "")).strip(),
    )
    _validate(cfg, path)
    return cfg


def _validate(cfg: SchoolConfig, path: Path) -> None:
    if not cfg.days:
        raise ConfigError(f"{path}: 'days' が空です")
    if not cfg.periods:
        raise ConfigError(f"{path}: 'periods' が空です")
    if not cfg.buildings:
        raise ConfigError(f"{path}: 'buildings' が空です")
    if not cfg.terms:
        raise ConfigError(f"{path}: 'terms' が空です")

    nos = cfg.period_numbers
    if len(set(nos)) != len(nos):
        raise ConfigError(f"{path}: periods.no が重複しています: {nos}")

    bnames = cfg.building_names
    if len(set(bnames)) != len(bnames):
        raise ConfigError(f"{path}: buildings.name が重複しています: {bnames}")

    for t in cfg.terms:
        if not t.always and not (t.start and t.end):
            raise ConfigError(
                f"{path}: term '{t.id}' は always:true か start/end のどちらかが必要です"
            )


def load_registry(path: str | Path) -> list[SchoolRef]:
    """``schools/index.json`` を読み込んで :class:`SchoolRef` の一覧を返す."""
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, list):
        raise ConfigError(f"{path}: トップレベルは配列である必要があります")
    refs = [
        SchoolRef(
            slug=str(e["slug"]),
            name=str(e.get("name", e["slug"])),
            short=str(e.get("short", "")),
            region=str(e.get("region", "")),
            status=str(e.get("status", "active")),
        )
        for e in raw
    ]
    slugs = [r.slug for r in refs]
    if len(set(slugs)) != len(slugs):
        raise ConfigError(f"{path}: slug が重複しています: {slugs}")
    return refs


def visible_schools(refs: Iterable[SchoolRef]) -> list[SchoolRef]:
    """トップページに出す学校（``status != 'hidden'``）だけを返す."""
    return [r for r in refs if r.status != "hidden"]
