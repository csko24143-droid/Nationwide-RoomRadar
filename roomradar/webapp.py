"""最小の Flask アプリ（テナント化のデモ／Phase 1 のサーバ描画版）.

1 つのコードベースで複数校をホストする薄い UI。空き判定（静的コア）は
:mod:`roomradar` のエンジンに、仮予約・報告（動的レイヤ）は
:class:`roomradar.live.LiveStore` に委譲する。学校固有値はすべて ``config.yml`` 由来。

ルーティング（DESIGN.md §6・パス方式）:
    ``/``                          全国トップ（学校一覧／レジストリ）
    ``/s/<slug>``                  その学校の空き教室検索
    ``/api/<slug>/reserve``        仮予約（POST）／``/reserve/cancel``／``/reserve/list``
    ``/api/<slug>/report``         使用中報告（POST）／``/report/cancel``
"""

from __future__ import annotations

import datetime
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from .config import ConfigError, SchoolConfig, load_registry, parse_school_config, visible_schools
from .live import LiveStore
from .school import LoadedSchool
from .validation import validate_school

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")

DEFAULT_SCHOOLS_DIR = Path("schools")
REPORT_THRESHOLD = 2  # この件数以上の報告で「使用中の可能性」表示（旧実装踏襲）
RATE_LIMIT, RATE_WINDOW = 30, 60  # 学校×IP あたり 60 秒で 30 回まで

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
 select, button, input {{ padding:9px 11px; border-radius:9px; border:1px solid #2c3458;
        background:#0f1320; color:#e8ecf5; font-size:15px; }}
 button {{ background: var(--accent); color:#0a0d18; border:0; font-weight:700; cursor:pointer; }}
 button.ghost {{ background:#232a44; color:#e8ecf5; }}
 .count {{ margin:14px 0 4px; color:#9aa3c4; }}
 .count b {{ color: var(--accent); font-size:20px; }}
 .bgroup {{ margin-top:14px; }}
 .bgroup h3 {{ font-size:14px; margin:0 0 8px; display:flex; align-items:center; gap:8px; }}
 .dot {{ width:11px; height:11px; border-radius:50%; display:inline-block; }}
 .rooms {{ display:flex; flex-wrap:wrap; gap:8px; }}
 details.room {{ background:#1d2440; border:1px solid #2c3458; border-radius:9px; min-width:96px; }}
 details.room[open] {{ min-width:230px; }}
 details.room.reported {{ opacity:.55; }}
 details.room > summary {{ padding:8px 12px; font-weight:600; cursor:pointer; list-style:none;
        display:flex; align-items:center; gap:6px; flex-wrap:wrap; }}
 details.room > summary::-webkit-details-marker {{ display:none; }}
 .badge {{ font-size:11px; padding:1px 6px; border-radius:999px; }}
 .badge.res {{ background:#2b3a6b; color:#bcd0ff; }}
 .badge.rep {{ background:#5a2b2b; color:#ffc9c9; }}
 .badge.warn {{ background:#7a3b1a; color:#ffd9b8; }}
 .actions {{ padding:0 12px 12px; display:flex; flex-direction:column; gap:6px; }}
 .actions input {{ width:100%; }}
 .actions .row {{ display:flex; gap:6px; }}
 .muted {{ color:#6b7393; }}
 footer {{ max-width:880px; margin:0 auto; padding:18px 20px; color:#6b7393; font-size:12px; }}
</style></head>
<body>
<header><div class="brand"><a href="/" style="text-decoration:none;color:inherit">Room<b>Radar</b></a>
 {subtitle}</div></header>
<main>{body}</main>
<footer>{footer}</footer>
{script}
</body></html>"""


def _esc(text) -> str:
    from markupsafe import escape

    return str(escape(text))


def create_app(schools_dir: str | Path = DEFAULT_SCHOOLS_DIR, live_db: str | Path = "live.db"):
    """Flask アプリを生成する（``flask`` はここで遅延 import）."""
    from flask import Flask, abort, jsonify, request

    schools_dir = Path(schools_dir)
    app = Flask(__name__)
    # DATABASE_URL があれば（PostgreSQL 等）それを優先。無ければ live_db（SQLite）。
    store = LiveStore(os.environ.get("DATABASE_URL") or str(live_db))
    _cache: dict[str, LoadedSchool] = {}
    _rate: dict[tuple[str, str], list[float]] = defaultdict(list)

    def get_school(slug: str) -> LoadedSchool:
        if slug not in _cache:
            _cache[slug] = LoadedSchool.load(slug, base_dir=schools_dir)
        return _cache[slug]

    def rate_limited(slug: str) -> bool:
        ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "")).split(",")[0].strip()
        now = time.time()
        hits = [t for t in _rate[(slug, ip)] if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            _rate[(slug, ip)] = hits
            return True
        hits.append(now)
        _rate[(slug, ip)] = hits
        return False

    def validate(cfg: SchoolConfig, day: str, period) -> int | None:
        """day/period を学校の許可集合で検証。OK なら整数 period を返す."""
        try:
            period = int(period)
        except (TypeError, ValueError):
            return None
        if day in cfg.days and period in cfg.period_numbers:
            return period
        return None

    # --- 画面 --------------------------------------------------------------
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
            '<p>空き教室をさがす学校を選んでください。'
            '<a href="/dashboard" style="float:right">運用ダッシュボード →</a></p>'
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
        sel_period = validate(cfg, sel_day, request.args.get("period") or def_period)
        if sel_period is None:
            sel_day, sel_period = def_day, def_period
        sel_building = request.args.get("building") or "all"
        if sel_day not in cfg.days:
            sel_day = cfg.days[0]

        building = None if sel_building == "all" else sel_building
        free = school.free_rooms(sel_day, sel_period, building=building)

        store.cleanup(school.now())
        reserve_counts = store.reservation_counts(slug, day=sel_day, period=sel_period)
        report_counts = store.report_counts(slug, day=sel_day, period=sel_period)

        body = _search_form(cfg, sel_day, sel_period, sel_building)
        body += f'<div class="count"><b>{len(free)}</b> 室 空き（{_esc(sel_day)} {sel_period}限）</div>'
        body += _rooms_by_building(cfg, free, reserve_counts, report_counts)
        subtitle = f'<span class="chip">{_esc(cfg.short_name)}</span>'
        footer = _esc(cfg.disclaimer) if cfg.disclaimer else ""
        script = _ACTION_JS.format(slug=_esc(slug), day=_esc(sel_day), period=sel_period,
                                   threshold=REPORT_THRESHOLD)
        return _render(f"{cfg.short_name} — RoomRadar", subtitle, body, cfg.accent, footer, script)

    @app.errorhandler(404)
    def not_found(_e):
        body = (
            '<div class="card"><p>そのページは見つかりませんでした。</p>'
            '<p><a href="/">学校一覧へ戻る</a></p></div>'
        )
        return _render("見つかりません — RoomRadar", "", body, "#6c8fff"), 404

    # --- API（動的レイヤ・学校スコープ） -----------------------------------
    def _require_school(slug: str) -> LoadedSchool:
        try:
            return get_school(slug)
        except FileNotFoundError:
            abort(404)

    @app.route("/api/<slug>/reserve", methods=["POST"])
    def api_reserve(slug: str):
        school = _require_school(slug)
        data = request.get_json(silent=True) or {}
        room = str(data.get("room", "")).strip()[:30]
        building = str(data.get("building", "")).strip()[:30]
        name = str(data.get("name", "")).strip()[:30]
        purpose = str(data.get("purpose", "")).strip()[:60]
        period = validate(school.config, data.get("day", ""), data.get("period"))
        if not room or not name or period is None:
            return jsonify({"ok": False, "error": "invalid"}), 400
        if rate_limited(slug):
            return jsonify({"ok": False, "error": "rate_limited"}), 429
        day = data.get("day")
        store.cleanup(school.now())
        expires = school.period_end(day, period).astimezone(datetime.timezone.utc).isoformat()
        code, count = store.reserve(
            slug, room=room, building=building, day=day, period=period,
            name=name, purpose=purpose, expires_at=expires,
        )
        return jsonify({"ok": True, "cancel_code": code, "count": count})

    @app.route("/api/<slug>/reserve/cancel", methods=["POST"])
    def api_reserve_cancel(slug: str):
        _require_school(slug)
        data = request.get_json(silent=True) or {}
        room = str(data.get("room", "")).strip()[:30]
        code = str(data.get("cancel_code", "")).strip()[:10]
        period = _as_int(data.get("period"))
        if not room or not code or period is None:
            return jsonify({"ok": False}), 400
        ok = store.cancel_reservation(slug, room=room, day=data.get("day", ""), period=period, cancel_code=code)
        return jsonify({"ok": ok})

    @app.route("/api/<slug>/reserve/list", methods=["GET"])
    def api_reserve_list(slug: str):
        school = _require_school(slug)
        period = validate(school.config, request.args.get("day", ""), request.args.get("period"))
        if period is None:
            return jsonify({"ok": False}), 400
        store.cleanup(school.now())
        return jsonify({"ok": True, "reservations": store.list_reservations(
            slug, day=request.args.get("day", ""), period=period)})

    @app.route("/api/<slug>/report", methods=["POST"])
    def api_report(slug: str):
        school = _require_school(slug)
        data = request.get_json(silent=True) or {}
        room = str(data.get("room", "")).strip()[:30]
        period = validate(school.config, data.get("day", ""), data.get("period"))
        if not room or period is None:
            return jsonify({"ok": False, "error": "invalid"}), 400
        if rate_limited(slug):
            return jsonify({"ok": False, "error": "rate_limited"}), 429
        day = data.get("day")
        store.cleanup(school.now())
        expires = school.period_end(day, period).astimezone(datetime.timezone.utc).isoformat()
        code, count = store.report(slug, room=room, day=day, period=period, expires_at=expires)
        return jsonify({"ok": True, "cancel_code": code, "count": count})

    @app.route("/api/<slug>/report/cancel", methods=["POST"])
    def api_report_cancel(slug: str):
        _require_school(slug)
        data = request.get_json(silent=True) or {}
        room = str(data.get("room", "")).strip()[:30]
        code = str(data.get("cancel_code", "")).strip()[:10]
        period = _as_int(data.get("period"))
        if not room or not code or period is None:
            return jsonify({"ok": False}), 400
        ok = store.cancel_report(slug, room=room, day=data.get("day", ""), period=period, cancel_code=code)
        return jsonify({"ok": ok})

    @app.route("/api/<slug>/counts", methods=["GET"])
    def api_counts(slug: str):
        """静的クライアント用：指定 曜日×時限 の教室別 予約数／報告数."""
        school = _require_school(slug)
        period = validate(school.config, request.args.get("day", ""), request.args.get("period"))
        if period is None:
            return jsonify({"ok": False}), 400
        day = request.args.get("day", "")
        store.cleanup(school.now())
        return jsonify({
            "ok": True,
            "reserve": store.reservation_counts(slug, day=day, period=period),
            "report": store.report_counts(slug, day=day, period=period),
            "threshold": REPORT_THRESHOLD,
        })

    # --- 運用ダッシュボード（学校横断・DESIGN ROADMAP フェーズ3） --------------
    repo_root = Path(__file__).resolve().parents[1]

    def _stats_doc() -> dict:
        """静的統計（dist/stats.json）＋ 稼働統計（予約・報告）を合算して返す."""
        path = repo_root / "dist" / "stats.json"
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
        else:  # 未ビルドでもレジストリから最低限を組み立てる
            refs = load_registry(schools_dir / "index.json")
            doc = {"totals": {"schools": len(refs), "rooms": 0, "lessons": 0},
                   "schools": [{"slug": r.slug, "name": r.name, "short": r.short,
                                "region": r.region, "status": r.status,
                                "rooms": 0, "lessons": 0, "buildings": 0,
                                "periods": 0, "days": 0, "terms": 0} for r in refs]}
        store.cleanup()
        live = store.active_by_school()
        for s in doc["schools"]:
            s["reservations"] = live.get(s["slug"], {}).get("reservations", 0)
            s["reports"] = live.get(s["slug"], {}).get("reports", 0)
        t = store.totals()
        doc["totals"]["reservations"] = t["reservations"]
        doc["totals"]["reports"] = t["reports"]
        return doc

    @app.route("/api/stats")
    def api_stats():
        return jsonify(_stats_doc())

    @app.route("/dashboard")
    def dashboard():
        doc = _stats_doc()
        t = doc["totals"]
        cards = "".join(
            f'<div class="card" style="display:inline-block;min-width:130px;margin-right:8px">'
            f'<div class="count"><b>{t.get(k, 0):,}</b></div><div class="muted">{label}</div></div>'
            for k, label in [
                ("schools", "学校"), ("rooms", "教室"), ("lessons", "コマ"),
                ("reservations", "予約(稼働中)"), ("reports", "報告(稼働中)"),
            ]
        )
        head = "".join(f"<th>{h}</th>" for h in
                       ["学校", "地域", "状態", "教室", "コマ", "校舎", "時限", "予約", "報告"])
        rows = ""
        for s in doc["schools"]:
            rows += (
                "<tr>"
                f'<td><a href="/s/{_esc(s["slug"])}">{_esc(s["name"])}</a></td>'
                f'<td>{_esc(s.get("region", ""))}</td><td>{_esc(s.get("status", ""))}</td>'
                f'<td>{s.get("rooms", 0):,}</td><td>{s.get("lessons", 0):,}</td>'
                f'<td>{s.get("buildings", 0)}</td><td>{s.get("periods", 0)}</td>'
                f'<td>{s.get("reservations", 0)}</td><td>{s.get("reports", 0)}</td>'
                "</tr>"
            )
        body = (
            "<h2 style='margin:6px 0'>運用ダッシュボード</h2>"
            '<p class="muted">プラットフォーム全体の規模と稼働状況（学校横断）。</p>'
            f"<div>{cards}</div>"
            '<table style="width:100%;border-collapse:collapse;margin-top:16px">'
            f'<thead><tr style="text-align:left;color:#9aa3c4;font-size:13px">{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table>"
            '<style>#dash td,#dash th{padding:8px;border-bottom:1px solid #232a44}</style>'
        )
        body = f'<div id="dash">{body}</div>'
        return _render("運用ダッシュボード — RoomRadar", "", body, "#6c8fff")

    # --- 管理UI（データ編集・ADMIN_TOKEN で保護・ROADMAP フェーズ3） ----------
    def _guard_admin() -> str:
        token = os.environ.get("ADMIN_TOKEN")
        if not token:
            abort(404)  # ADMIN_TOKEN 未設定なら機能無効（安全側の既定）
        given = request.values.get("token") or request.headers.get("X-Admin-Token")
        if given != token:
            abort(403)
        return token

    def _safe_school_dir(slug: str) -> Path:
        if not _SLUG_RE.match(slug or ""):
            abort(404)
        d = schools_dir / slug
        if d.resolve().parent != schools_dir.resolve() or not (d / "config.yml").exists():
            abort(404)
        return d

    @app.route("/admin")
    def admin_home():
        token = _guard_admin()
        refs = load_registry(schools_dir / "index.json")
        rows = ""
        for r in refs:
            errors, warnings = validate_school(r.slug, schools_dir)
            badge = (
                "<span style='color:#7ee0a6'>OK</span>"
                if not errors
                else f"<span style='color:#ff9a9a'>NG {len(errors)}</span>"
            )
            rows += (
                f"<tr><td><a href='/admin/{_esc(r.slug)}?token={_esc(token)}'>{_esc(r.name)}</a></td>"
                f"<td>{_esc(r.slug)}</td><td>{badge}</td><td>{len(warnings)}</td></tr>"
            )
        body = (
            "<h2 style='margin:6px 0'>管理コンソール</h2>"
            "<p class='muted'>学校設定（config.yml）の検証・編集。保存はこのサーバのファイルへ書き込みます"
            "（永続化するには git にコミットしてください）。</p>"
            "<table id='dash' style='width:100%;border-collapse:collapse'>"
            "<thead><tr style='text-align:left;color:#9aa3c4'><th>学校</th><th>slug</th>"
            "<th>検証</th><th>警告</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "<style>#dash td,#dash th{padding:8px;border-bottom:1px solid #232a44}</style>"
        )
        return _render("管理コンソール — RoomRadar", "", body, "#6c8fff")

    @app.route("/admin/<slug>")
    def admin_school(slug: str):
        token = _guard_admin()
        d = _safe_school_dir(slug)
        content = (d / "config.yml").read_text(encoding="utf-8")
        return _render(*_admin_edit_view(slug, token, content, schools_dir))

    @app.route("/admin/<slug>/config", methods=["POST"])
    def admin_save_config(slug: str):
        token = _guard_admin()
        d = _safe_school_dir(slug)
        content = request.form.get("content", "")
        try:
            cfg = parse_school_config(content, source=f"{slug}/config.yml")
        except (ConfigError, KeyError, ValueError, TypeError) as exc:
            return _render(*_admin_edit_view(slug, token, content, schools_dir,
                                             error=f"保存しませんでした: {exc}"))
        if cfg.slug != slug:
            return _render(*_admin_edit_view(slug, token, content, schools_dir,
                                             error=f"slug は '{slug}' のままにしてください（'{cfg.slug}' へは変更不可）"))
        tmp = d / "config.yml.tmp"
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, d / "config.yml")
        _cache.pop(slug, None)  # 次のアクセスで再読込
        return _render(*_admin_edit_view(slug, token, content, schools_dir, saved=True))

    # --- 静的コアのクライアント（web/）とビルド成果物（dist/）の配信 ----------
    from flask import send_from_directory

    web_dir, dist_dir = repo_root / "web", repo_root / "dist"

    @app.route("/app/")
    @app.route("/app/<path:filename>")
    def app_client(filename: str = "index.html"):
        return send_from_directory(web_dir, filename)

    @app.route("/dist/<path:filename>")
    def dist_file(filename: str):
        return send_from_directory(dist_dir, filename)

    return app


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _render(title, subtitle, body, accent, footer="", script="") -> str:
    return _PAGE.format(
        title=_esc(title), subtitle=subtitle, body=body, accent=accent, footer=footer, script=script
    )


def _admin_edit_view(slug, token, content, schools_dir, *, error=None, saved=False):
    """管理UIの config.yml 編集画面（_render に渡す (title, subtitle, body, accent)）."""
    errors, warnings = validate_school(slug, schools_dir)
    banner = ""
    if error:
        banner = f"<div class='card' style='border-color:#7a3b1a'>⚠ {_esc(error)}</div>"
    elif saved:
        banner = "<div class='card' style='border-color:#2e6b4a'>✓ 保存しました（下に検証結果）</div>"

    if errors:
        val = "<div class='card'><b style='color:#ff9a9a'>検証エラー</b><ul>" + "".join(
            f"<li>{_esc(e)}</li>" for e in errors[:30]
        ) + "</ul></div>"
    else:
        val = "<div class='card muted'>検証OK（エラーなし）</div>"
    if warnings:
        val += "<details class='card'><summary>警告 " + str(len(warnings)) + " 件</summary><ul>" + "".join(
            f"<li>{_esc(w)}</li>" for w in warnings[:30]
        ) + "</ul></details>"

    form = (
        f"<form method='post' action='/admin/{_esc(slug)}/config'>"
        f"<input type='hidden' name='token' value='{_esc(token)}'>"
        "<textarea name='content' spellcheck='false' style='width:100%;height:340px;"
        "font-family:ui-monospace,monospace;font-size:13px;padding:10px;border-radius:9px;"
        f"border:1px solid #2c3458;background:#0f1320;color:#e8ecf5'>{_esc(content)}</textarea>"
        "<div style='margin-top:8px'><button type='submit'>検証して保存</button> "
        f"<a href='/admin?token={_esc(token)}' class='muted' style='margin-left:10px'>← 一覧へ</a></div></form>"
    )
    body = f"<h2 style='margin:6px 0'>{_esc(slug)} / config.yml</h2>{banner}{form}{val}"
    return (f"管理 {slug} — RoomRadar", "", body, "#6c8fff")


def _search_form(cfg: SchoolConfig, sel_day: str, sel_period: int, sel_building: str) -> str:
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
        '<div><button type="submit">検索</button></div>'
        "</form>"
    )


def _room_panel(room_name: str, building: str, reserves: int, reports: int) -> str:
    """1 教室分の details パネル（件数バッジ＋予約/報告アクション）."""
    badges = ""
    if reserves:
        badges += f'<span class="badge res">予約{reserves}</span>'
    if reports:
        badges += f'<span class="badge rep">報告{reports}</span>'
    cls = "room reported" if reports >= REPORT_THRESHOLD else "room"
    warn = '<span class="badge warn">使用中の可能性</span>' if reports >= REPORT_THRESHOLD else ""
    rn = _esc(room_name)
    return (
        f'<details class="{cls}" data-room="{rn}" data-building="{_esc(building)}">'
        f"<summary>{rn}{badges}{warn}</summary>"
        '<div class="actions">'
        f'<input class="r-name" placeholder="お名前/グループ（任意・実名非推奨）" maxlength="30">'
        f'<input class="r-purpose" placeholder="用途（任意）" maxlength="60">'
        '<div class="row">'
        '<button class="act-reserve" type="button">仮予約する</button>'
        '<button class="act-report ghost" type="button">⚠ 実は使用中</button>'
        "</div>"
        '<div class="row">'
        '<button class="act-reserve-cancel ghost" type="button" hidden>予約を取消</button>'
        '<button class="act-report-cancel ghost" type="button" hidden>報告を取消</button>'
        "</div>"
        "</div></details>"
    )


def _rooms_by_building(cfg: SchoolConfig, free, reserve_counts, report_counts) -> str:
    if not free:
        return '<div class="card muted">この時間に空いている教室はありません。</div>'
    out = []
    for b in cfg.buildings:
        rooms = [r for r in free if r.building == b.name]
        if not rooms:
            continue
        chips = "".join(
            _room_panel(r.room, r.building, reserve_counts.get(r.room, 0), report_counts.get(r.room, 0))
            for r in rooms
        )
        out.append(
            f'<div class="bgroup"><h3><span class="dot" style="background:{b.color}"></span>'
            f'{_esc(b.name)} <span class="muted">{len(rooms)}</span></h3>'
            f'<div class="rooms">{chips}</div></div>'
        )
    known = {b.name for b in cfg.buildings}
    extra = [r for r in free if r.building not in known]
    if extra:
        chips = "".join(
            _room_panel(r.room, r.building, reserve_counts.get(r.room, 0), report_counts.get(r.room, 0))
            for r in extra
        )
        out.append(f'<div class="bgroup"><h3>その他</h3><div class="rooms">{chips}</div></div>')
    return "".join(out)


# クライアント側：予約・報告アクション（学校スコープの API を叩く）。
_ACTION_JS = """<script>
(function() {{
  const SLUG = "{slug}", DAY = "{day}", PERIOD = {period}, THRESHOLD = {threshold};
  const key = (kind, room) => `${{kind}}_${{SLUG}}_${{room}}_${{DAY}}_${{PERIOD}}`;
  async function post(path, payload) {{
    const res = await fetch(`/api/${{SLUG}}/${{path}}`, {{
      method: "POST", headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }});
    return res.json().catch(() => ({{ ok: false }}));
  }}
  // 既に自分が予約/報告済みの教室は取消ボタンを出す
  function syncButtons(panel) {{
    const room = panel.dataset.room;
    panel.querySelector(".act-reserve-cancel").hidden = !localStorage.getItem(key("reserve", room));
    panel.querySelector(".act-report-cancel").hidden = !localStorage.getItem(key("report", room));
  }}
  document.querySelectorAll("details.room").forEach(syncButtons);

  document.addEventListener("click", async (e) => {{
    const btn = e.target.closest("button");
    if (!btn) return;
    const panel = btn.closest("details.room");
    if (!panel) return;
    const room = panel.dataset.room, building = panel.dataset.building;
    const base = {{ room, day: DAY, period: PERIOD }};

    if (btn.classList.contains("act-reserve")) {{
      const name = (panel.querySelector(".r-name").value || "").trim() || "匿名";
      const purpose = (panel.querySelector(".r-purpose").value || "").trim();
      const d = await post("reserve", {{ ...base, building, name, purpose }});
      if (d.ok) {{ localStorage.setItem(key("reserve", room), d.cancel_code); location.reload(); }}
      else alert(d.error === "rate_limited" ? "操作が多すぎます。少し待ってください。" : "予約できませんでした。");
    }} else if (btn.classList.contains("act-report")) {{
      const d = await post("report", base);
      if (d.ok) {{ localStorage.setItem(key("report", room), d.cancel_code); location.reload(); }}
      else alert(d.error === "rate_limited" ? "操作が多すぎます。少し待ってください。" : "報告できませんでした。");
    }} else if (btn.classList.contains("act-reserve-cancel")) {{
      const code = localStorage.getItem(key("reserve", room));
      const d = await post("reserve/cancel", {{ ...base, cancel_code: code }});
      if (d.ok) {{ localStorage.removeItem(key("reserve", room)); location.reload(); }}
    }} else if (btn.classList.contains("act-report-cancel")) {{
      const code = localStorage.getItem(key("report", room));
      const d = await post("report/cancel", {{ ...base, cancel_code: code }});
      if (d.ok) {{ localStorage.removeItem(key("report", room)); location.reload(); }}
    }}
  }});
}})();
</script>"""
