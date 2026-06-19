/*
 * RoomRadar 空き判定（クライアント側）.
 *
 * roomradar/availability.py・terms.py を JavaScript へ移植した純粋関数群。
 * ブラウザ（<script> で window.RoomRadar）でも Node（require）でも動く UMD。
 * DESIGN.md §4.1「静的コア」：ビルド済み JSON を読んでブラウザ側で空きを計算する。
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RoomRadar = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function parseMD(s) {
    const parts = String(s).split("-");
    return [Number(parts[0]), Number(parts[1])];
  }
  function cmpMD(a, b) {
    return a[0] - b[0] || a[1] - b[1];
  }

  // today が start〜end（両端含む）に入るか。start>end は年末跨ぎ。
  function inSeason(today, start, end) {
    if (cmpMD(start, end) <= 0) return cmpMD(start, today) <= 0 && cmpMD(today, end) <= 0;
    return cmpMD(today, start) >= 0 || cmpMD(today, end) <= 0;
  }

  // 有効な学期 id の一覧（config 定義順）。
  function activeTerms(terms, date) {
    date = date || new Date();
    const today = [date.getMonth() + 1, date.getDate()];
    const out = [];
    for (const t of terms || []) {
      if (t.always) out.push(t.id);
      else if (t.start && t.end && inSeason(today, parseMD(t.start), parseMD(t.end))) out.push(t.id);
    }
    return out;
  }

  // 指定 曜日×時限 の空き教室。Python 版 free_rooms と同じ結果・同じ並び。
  function freeRooms(data, opts) {
    opts = opts || {};
    const day = opts.day;
    const period = String(opts.period);
    const building = opts.building || null;
    const today = opts.today || new Date();

    const active = new Set(activeTerms(data.terms, today));
    const occupied = new Set();
    const occ = data.occupied || {};
    for (const term of Object.keys(occ)) {
      if (!active.has(term)) continue;
      const rooms = (((occ[term] || {})[day] || {})[period]) || [];
      for (const r of rooms) occupied.add(r);
    }

    const order = new Map((data.buildings || []).map((b, i) => [b.name, i]));
    const fallback = order.size;
    const cand = (data.rooms || []).filter(
      (r) => !occupied.has(r.room) && (!building || r.building === building)
    );
    cand.sort((a, b) => {
      const oa = order.has(a.building) ? order.get(a.building) : fallback;
      const ob = order.has(b.building) ? order.get(b.building) : fallback;
      if (oa !== ob) return oa - ob;
      return a.room < b.room ? -1 : a.room > b.room ? 1 : 0;
    });
    return cand;
  }

  // 現在の曜日・時限（検索の初期値）。
  function currentDayPeriod(data, now) {
    now = now || new Date();
    const names = ["月", "火", "水", "木", "金", "土", "日"]; // 0=月 … 6=日
    let day = names[(now.getDay() + 6) % 7]; // JS: 0=日
    if (!data.days.includes(day)) day = data.days[0];
    const hhmm =
      String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");
    let period = data.periods[0].period;
    for (const p of data.periods) {
      if (p.start <= hhmm && hhmm <= p.end) {
        period = p.period;
        break;
      }
    }
    return { day: day, period: period };
  }

  return {
    activeTerms: activeTerms,
    inSeason: inSeason,
    freeRooms: freeRooms,
    currentDayPeriod: currentDayPeriod,
  };
});
