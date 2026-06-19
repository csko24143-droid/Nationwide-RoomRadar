"""最小の Flask アプリ（テナント化のデモ／Phase 1 のサーバ描画版）.

1 つのコードベースで複数校をホストすることを示す薄い UI。空き判定は
:mod:`roomradar` のエンジンに委譲し、学校固有値はすべて ``config.yml`` 由来。

ルーティング（DESIGN.md §6・パス方式）:
    ``/``            全国トップ（学校一覧／レジストリ）
    ``/s/<slug>``    その学校の空き教室検索

予約・報告などの動的レイヤ（DESIGN §5.4）は本 MVP には未実装。
"""

from __future__ import annotations

from pathlib import Path

from .config import load_registry, visible_schools
from .school import LoadedSchool

DEFAULT_SCHOOLS_DIR = Path("schools")

_PAGE = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
 :root {{ --accent: {accent}; }}
 * {{ box-sizing: border-box; }}
 body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0;
        background:#0f1320; color:#e8ecf5; }}
 a {{ color: var(--accent); }}
 header {{ background:#161b2e; padding:16px 20px; border-bottom:1px solid #232a44; }}
 header .brand {{ font-weight:700; font-size:18px; }}
 header .brand b {{ color: var(--accent); }}
 main {{ max-width: 880px; margin: 0 auto; padding: 20px; }}
 .chip {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px;
         background:#232a44; color:#aeb6d4; margin-left:6px; }}
 .card {{ background:#161b2e; border:1px solid #232a44; border-radius:12px;
         padding:14px 16px; margin:10px 0; }}
 .card a.school {{ font-size:17px; font-weight:600; text-decoration:none; }}
 form.search {{ display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end; margin:12px 0 4px; }}
 label {{ display:block; font-size:12px; color:#9aa3c4; margin-bottom:4px; }}
 select, button {{ padding:9px 11px; border-radius:9px; border:1px solid #2c3458;
        background:#0f1320; color:#e8ecf5; font-size:15px; }}
 button {{ background: var(--accent); color:#0a0d18; border:0; font-weight:700; cursor:pointer; }}
 .count {{ margin:14px 0 4px; color:#9aa3c4; }}
 .count b {{ color: var(--accent); font-size:20px; }}
 .bgroup {{ margin-top:14px; }}
 .bgroup h3 {{ font-size:14px; margin:0 0 8px; display:flex; align-items:center; gap:8px; }}
 .dot {{ width:11px; height:11px; border-radius:50%; display:inline-block; }}
 .rooms {{ display:flex; flex-wrap:wrap; gap:8px; }}
 .room {{ background:#1d2440; border:1px solid #2c3458; border-radius:9px;
         padding:8px 12px; font-weight:600; }}
 .muted {{ color:#6b7393; }}
 footer {{ max-width:880px; margin:0 auto; padding:18px 20px; color:#6b7393; font-size:12px; }}
</style></head>
<body>
<header><div class="brand"><a href="/" style="text-decoration:none;color:inherit">Room<b>Radar</b></a>
 {subtitle}</div></header>
<main>{body}</main>
<footer>{footer}</footer>
</body></html>"""


def _esc(text: str) -> str:
    from markupsafe import escape

    return str(escape(text))


def create_app(schools_dir: str | Path = DEFAULT_SCHOOLS_DIR):
    """Flask アプリを生成する（``flask`` はここで遅延 import）."""
    from flask import Flask, abort, request

    schools_dir = Path(schools_dir)
    app = Flask(__name__)
    _cache: dict[str, LoadedSchool] = {}

    def get_school(slug: str) -> LoadedSchool:
        if slug not in _cache:
            _cache[slug] = LoadedSchool.load(slug, base_dir=schools_dir)
        return _cache[slug]

    @app.route("/")
    def home():
        refs = visible_schools(load_registry(schools_dir / "index.json"))
        cards = []
        for r in refs:
            badge = "" if r.status == "active" else f'<span class="chip">{_esc(r.status)}</span>'
            region = f'<span class="chip">{_esc(r.region)}</span>' if r.region else ""
            cards.append(
                f'<div class="card"><a class="school" href="/s/{_esc(r.slug)}">'
                f"{_esc(r.name)}</a>{region}{badge}</div>"
            )
        body = (
            "<p>空き教室をさがす学校を選んでください。</p>"
            + "".join(cards)
            + '<div class="card muted">自分の学校を追加したいですか？ '
            "<code>schools/&lt;slug&gt;/</code> にデータを追加するだけで載せられます"
            "（<a href=\"https://github.com/csko24143-droid/Nationwide-RoomRadar/blob/main/docs/data-import-format.md\">データ形式</a>）。</div>"
        )
        return _render("RoomRadar — 全国の空き教室さがし", "", body, "#6c8fff")

    @app.route("/s/<slug>")
    def school_page(slug: str):
        try:
            school = get_school(slug)
        except FileNotFoundError:
            abort(404)
        cfg = school.config

        def_day, def_period = school.current_day_period()
        sel_day = request.args.get("day") or def_day
        sel_period_raw = request.args.get("period")
        sel_period = int(sel_period_raw) if (sel_period_raw or "").isdigit() else def_period
        sel_building = request.args.get("building") or "all"
        if sel_day not in cfg.days:
            sel_day = cfg.days[0]
        if sel_period not in cfg.period_numbers:
            sel_period = cfg.period_numbers[0]

        building = None if sel_building == "all" else sel_building
        free = school.free_rooms(sel_day, sel_period, building=building)

        body = _search_form(cfg, sel_day, sel_period, sel_building)
        body += f'<div class="count"><b>{len(free)}</b> 室 空き（{_esc(sel_day)} {sel_period}限）</div>'
        body += _rooms_by_building(cfg, free)
        subtitle = f'<span class="chip">{_esc(cfg.short_name)}</span>'
        footer = _esc(cfg.disclaimer) if cfg.disclaimer else ""
        return _render(f"{cfg.short_name} — RoomRadar", subtitle, body, cfg.accent, footer)

    @app.errorhandler(404)
    def not_found(_e):
        body = (
            '<div class="card"><p>そのページは見つかりませんでした。</p>'
            '<p><a href="/">学校一覧へ戻る</a></p></div>'
        )
        return _render("見つかりません — RoomRadar", "", body, "#6c8fff"), 404

    return app


def _render(title: str, subtitle: str, body: str, accent: str, footer: str = "") -> str:
    return _PAGE.format(title=_esc(title), subtitle=subtitle, body=body, accent=accent, footer=footer)


def _search_form(cfg, sel_day: str, sel_period: int, sel_building: str) -> str:
    days = "".join(
        f'<option value="{_esc(d)}"{" selected" if d == sel_day else ""}>{_esc(d)}</option>'
        for d in cfg.days
    )
    periods = "".join(
        f'<option value="{p.number}"{" selected" if p.number == sel_period else ""}>'
        f"{p.number}限 {p.start}–{p.end}</option>"
        for p in cfg.periods
    )
    blds = '<option value="all">すべての校舎</option>' + "".join(
        f'<option value="{_esc(b.name)}"{" selected" if b.name == sel_building else ""}>'
        f"{_esc(b.name)}</option>"
        for b in cfg.buildings
    )
    return (
        '<form class="search" method="get">'
        f'<div><label>曜日</label><select name="day">{days}</select></div>'
        f'<div><label>時限</label><select name="period">{periods}</select></div>'
        f'<div><label>校舎</label><select name="building">{blds}</select></div>'
        "<div><button type=\"submit\">検索</button></div>"
        "</form>"
    )


def _rooms_by_building(cfg, free) -> str:
    if not free:
        return '<div class="card muted">この時間に空いている教室はありません。</div>'
    color = {b.name: b.color for b in cfg.buildings}
    out = []
    for b in cfg.buildings:
        rooms = [r for r in free if r.building == b.name]
        if not rooms:
            continue
        chips = "".join(f'<span class="room">{_esc(r.room)}</span>' for r in rooms)
        out.append(
            f'<div class="bgroup"><h3><span class="dot" style="background:{b.color}"></span>'
            f"{_esc(b.name)} <span class=\"muted\">{len(rooms)}</span></h3>"
            f'<div class="rooms">{chips}</div></div>'
        )
    # config の buildings に無い校舎（データ側のみ）も拾う
    known = set(color)
    extra = [r for r in free if r.building not in known]
    if extra:
        chips = "".join(f'<span class="room">{_esc(r.room)}</span>' for r in extra)
        out.append(f'<div class="bgroup"><h3>その他</h3><div class="rooms">{chips}</div></div>')
    return "".join(out)
