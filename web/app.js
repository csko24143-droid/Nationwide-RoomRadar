/*
 * RoomRadar 静的クライアント（学校ページ）.
 *
 * ビルド済み JSON（/dist/schools/<slug>.json）を読み、空き判定を
 * availability.js（= Python エンジンと同一ロジック）でブラウザ側で計算する。
 * 予約・報告（動的レイヤ）だけ /api/<slug>/... を呼ぶ（DESIGN.md §4.1）。
 */
(function () {
  "use strict";
  const DIST = window.ROOMRADAR_DIST || "/dist";
  // API が空文字（静的配信・バックエンド無し）なら「検索のみ」。未定義はサーバ既定 /api。
  const API = typeof window.ROOMRADAR_API === "string" ? window.ROOMRADAR_API : "/api";
  const HAS_BACKEND = API !== "";
  const params = new URLSearchParams(location.search);
  const slug = params.get("school");

  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  let data = null;
  const sel = { day: null, period: null, building: "all" };

  if (!slug) {
    $("results").innerHTML = '<div class="card">学校が指定されていません。<a href="index.html">一覧へ</a></div>';
    return;
  }

  // まず index.json でバージョン（v）を引き、?v=… を付けてキャッシュバスティング
  fetch(`${DIST}/index.json`)
    .then((r) => r.json())
    .then((index) => {
      const entry = (index || []).find((s) => s.slug === slug) || {};
      const v = entry.v ? `?v=${entry.v}` : "";
      return fetch(`${DIST}/schools/${encodeURIComponent(slug)}.json${v}`);
    })
    .then((r) => {
      if (!r.ok) throw new Error("not found");
      return r.json();
    })
    .then((d) => {
      data = d;
      document.documentElement.style.setProperty("--accent", d.accent || "#6c8fff");
      document.title = `${d.short_name} — RoomRadar`;
      const chip = $("school-chip");
      chip.textContent = d.short_name;
      chip.hidden = false;
      const meta = [];
      if (d.data_updated) meta.push("データ最終更新: " + d.data_updated);
      if (d.source) meta.push("出典: " + d.source);
      let footer = meta.join(" ／ ");
      if (d.disclaimer) footer += (footer ? "  " : "") + d.disclaimer;
      $("footer").textContent = footer;

      const cur = RoomRadar.currentDayPeriod(d);
      sel.day = data.days.includes(params.get("day")) ? params.get("day") : cur.day;
      const pq = parseInt(params.get("period"), 10);
      sel.period = data.periods.some((p) => p.period === pq) ? pq : cur.period;
      const bq = params.get("building");
      sel.building = bq && data.buildings.some((b) => b.name === bq) ? bq : "all";

      renderForm();
      render();
    })
    .catch(() => {
      $("results").innerHTML =
        '<div class="card">この学校のデータを読み込めませんでした。<a href="index.html">一覧へ</a></div>';
    });

  function renderForm() {
    const days = data.days
      .map((d) => `<option value="${esc(d)}"${d === sel.day ? " selected" : ""}>${esc(d)}</option>`)
      .join("");
    const periods = data.periods
      .map(
        (p) =>
          `<option value="${p.period}"${p.period === sel.period ? " selected" : ""}>${p.period}限 ${p.start}–${p.end}</option>`
      )
      .join("");
    const blds =
      '<option value="all">すべての校舎</option>' +
      data.buildings
        .map((b) => `<option value="${esc(b.name)}"${b.name === sel.building ? " selected" : ""}>${esc(b.name)}</option>`)
        .join("");
    $("search").innerHTML =
      '<form class="search" id="form">' +
      `<div><label>曜日</label><select name="day">${days}</select></div>` +
      `<div><label>時限</label><select name="period">${periods}</select></div>` +
      `<div><label>校舎</label><select name="building">${blds}</select></div>` +
      "</form>";
    // 選択変更で即再計算（送信ボタン不要）
    $("form").addEventListener("change", (e) => {
      const f = e.currentTarget;
      sel.day = f.day.value;
      sel.period = parseInt(f.period.value, 10);
      sel.building = f.building.value;
      const q = new URLSearchParams({ school: slug, day: sel.day, period: sel.period, building: sel.building });
      history.replaceState(null, "", `?${q}`);
      render();
    });
  }

  function render() {
    const building = sel.building === "all" ? null : sel.building;
    const free = RoomRadar.freeRooms(data, { day: sel.day, period: sel.period, building });
    $("count").innerHTML = `<b>${free.length}</b> 室 空き（${esc(sel.day)} ${sel.period}限）`;

    if (!HAS_BACKEND) {
      renderRooms(free, { reserve: {}, report: {}, threshold: 2 });
      return;
    }
    fetch(`${API}/${encodeURIComponent(slug)}/counts?day=${encodeURIComponent(sel.day)}&period=${sel.period}`)
      .then((r) => r.json())
      .then((c) => renderRooms(free, c.ok ? c : { reserve: {}, report: {}, threshold: 2 }))
      .catch(() => renderRooms(free, { reserve: {}, report: {}, threshold: 2 }));
  }

  function panel(room, building, reserves, reports, threshold) {
    let badges = "";
    if (reserves) badges += `<span class="badge res">予約${reserves}</span>`;
    if (reports) badges += `<span class="badge rep">報告${reports}</span>`;
    const reported = reports >= threshold;
    const warn = reported ? '<span class="badge warn">使用中の可能性</span>' : "";
    const rn = esc(room);
    return (
      `<details class="room${reported ? " reported" : ""}" data-room="${rn}" data-building="${esc(building)}">` +
      `<summary>${rn}${badges}${warn}</summary>` +
      '<div class="actions">' +
      '<input class="r-name" placeholder="お名前/グループ（任意・実名非推奨）" maxlength="30">' +
      '<input class="r-purpose" placeholder="用途（任意）" maxlength="60">' +
      '<div class="row"><button class="act-reserve" type="button">仮予約する</button>' +
      '<button class="act-report ghost" type="button">⚠ 実は使用中</button></div>' +
      '<div class="row"><button class="act-reserve-cancel ghost" type="button" hidden>予約を取消</button>' +
      '<button class="act-report-cancel ghost" type="button" hidden>報告を取消</button></div>' +
      "</div></details>"
    );
  }

  function chipFor(r, counts, threshold) {
    // バックエンドが無い静的配信では、操作なしのプレーンなチップで表示。
    if (!HAS_BACKEND) return `<span class="room-chip">${esc(r.room)}</span>`;
    return panel(r.room, r.building, counts.reserve[r.room] || 0, counts.report[r.room] || 0, threshold);
  }

  function renderRooms(free, counts) {
    const threshold = counts.threshold || 2;
    if (!free.length) {
      $("results").innerHTML = '<div class="card muted">この時間に空いている教室はありません。</div>';
      return;
    }
    const groups = [];
    const known = new Set(data.buildings.map((b) => b.name));
    for (const b of data.buildings) {
      const rooms = free.filter((r) => r.building === b.name);
      if (!rooms.length) continue;
      const chips = rooms.map((r) => chipFor(r, counts, threshold)).join("");
      groups.push(
        `<div class="bgroup"><h3><span class="dot" style="background:${b.color}"></span>${esc(b.name)} <span class="muted">${rooms.length}</span></h3><div class="rooms">${chips}</div></div>`
      );
    }
    const extra = free.filter((r) => !known.has(r.building));
    if (extra.length) {
      const chips = extra.map((r) => chipFor(r, counts, threshold)).join("");
      groups.push(`<div class="bgroup"><h3>その他</h3><div class="rooms">${chips}</div></div>`);
    }
    $("results").innerHTML = groups.join("");
    if (HAS_BACKEND) document.querySelectorAll("details.room").forEach(syncCancelButtons);
  }

  function key(kind, room) {
    return `${kind}_${slug}_${room}_${sel.day}_${sel.period}`;
  }
  function syncCancelButtons(p) {
    const room = p.dataset.room;
    p.querySelector(".act-reserve-cancel").hidden = !localStorage.getItem(key("reserve", room));
    p.querySelector(".act-report-cancel").hidden = !localStorage.getItem(key("report", room));
  }

  async function post(path, payload) {
    try {
      const res = await fetch(`${API}/${encodeURIComponent(slug)}/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      return await res.json();
    } catch (_) {
      return { ok: false };
    }
  }

  document.addEventListener("click", async (e) => {
    if (!HAS_BACKEND) return; // 静的配信では予約・報告は無効
    const btn = e.target.closest("button");
    if (!btn) return;
    const p = btn.closest("details.room");
    if (!p) return;
    const room = p.dataset.room,
      building = p.dataset.building;
    const base = { room, day: sel.day, period: sel.period };

    if (btn.classList.contains("act-reserve")) {
      const name = (p.querySelector(".r-name").value || "").trim() || "匿名";
      const purpose = (p.querySelector(".r-purpose").value || "").trim();
      const d = await post("reserve", Object.assign({}, base, { building, name, purpose }));
      if (d.ok) {
        localStorage.setItem(key("reserve", room), d.cancel_code);
        render();
      } else alert(d.error === "rate_limited" ? "操作が多すぎます。少し待ってください。" : "予約できませんでした。");
    } else if (btn.classList.contains("act-report")) {
      const d = await post("report", base);
      if (d.ok) {
        localStorage.setItem(key("report", room), d.cancel_code);
        render();
      } else alert(d.error === "rate_limited" ? "操作が多すぎます。少し待ってください。" : "報告できませんでした。");
    } else if (btn.classList.contains("act-reserve-cancel")) {
      const d = await post("reserve/cancel", Object.assign({}, base, { cancel_code: localStorage.getItem(key("reserve", room)) }));
      if (d.ok) {
        localStorage.removeItem(key("reserve", room));
        render();
      }
    } else if (btn.classList.contains("act-report-cancel")) {
      const d = await post("report/cancel", Object.assign({}, base, { cancel_code: localStorage.getItem(key("report", room)) }));
      if (d.ok) {
        localStorage.removeItem(key("report", room));
        render();
      }
    }
  });
})();
