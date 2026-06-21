# ロードマップ / 実装チェックリスト

[`DESIGN.md`](./DESIGN.md) §14 のフェーズを、実装タスクへ落とし込んだもの。
チェックは進捗に応じて更新する。

---

## フェーズ0 — 設計（本書群）✅ 進行中
- [x] 現状分析（ハードコード箇所・既知の不具合の洗い出し）
- [x] アーキテクチャ方針（静的コア＋動的レイヤ）
- [x] データモデル・設定スキーマの定義
- [x] データ投入方式の決定（ファイル方式を推奨採用）
- [ ] 時限時刻の正値確認（Python版/JS版どちらが正か）← 未確定。config の値は Python 版
- [x] 独自ドメイン/ルーティング方式 → **パス方式 `/s/<slug>` を採用**（DESIGN §6）
- [ ] フロント統合の方針A/B 決定 ← 当面 **方針B（サーバ描画）** で着手。フェーズ2でAへ

## フェーズ1 — テナント化MVP（1コードで複数校・NUST移行込み）
- [x] `schools/index.json` と `schools/<slug>/config.yml` のローダ（`roomradar/config.py`）
- [x] 検索ロジックの汎用化（校舎別 if 分岐の撤去、差集合を学校非依存に）（`roomradar/availability.py`）
- [x] 時限・学期・曜日・校舎・色・学校名を config から注入（ハードコード排除）
- [x] 時限時刻の単一ソース化（config → サーバ／テンプレ。JS側はフェーズ2で供給）
- [x] 学期判定の汎用化（年跨ぎ対応の純粋関数 `roomradar/terms.py`）
- [x] API を `/api/<slug>/…` 化、入力検証を学校別許可集合に（`roomradar/webapp.py`）
- [x] 予約・報告DBへ `school` 列追加＋複合インデックス、localStorage キー拡張（`roomradar/live.py`）
- [x] 全国トップページ（学校一覧）＋各校検索（`roomradar/webapp.py`）
- [x] NUST 移行：DB→CSV エクスポート、config 作成、**旧実装と全36コマで一致を検証**（`scripts/export_nust.py`）

## フェーズ2 — 静的コア化＋貢献導線
- [x] 空き計算のクライアント化（学校別 `dist/schools/<slug>.json` を配信・`web/availability.js`）
- [x] `scripts/build.py`（配信用 JSON・index 生成）
- [x] フロント：静的クライアント（方針A・`web/`）を追加。サーバ描画（方針B）と併存
- [x] JS 計算とサーバ計算の一致をテストで担保（`tests/test_client_js.py`・Node クロスチェック）
- [x] `scripts/validate.py`（フォーマット検証・取り込み時の自動チェック）
- [x] CI で検証自動化（`.github/workflows/ci.yml`：validate→build→test、PR時に自動実行）
- [x] `CONTRIBUTING.md` ／ Issue テンプレ「学校追加」（`.github/ISSUE_TEMPLATE/add-school.yml`）
- [x] キャッシュバージョニング（`?v=<内容ハッシュ>`＋`/dist` の Cache-Control）／ CDN・静的配信手順（`docs/DEPLOY.md`）
- [x] 非技術者向けフォーム導線（`web/add-school.html` → GitHub Issue 自動生成）

## フェーズ3 — スケール運用（数十〜数百校）
- [x] 解析ダッシュボードの学校横断対応（`/dashboard`・`/api/stats`・`dist/stats.json`）
- [x] ストレージ抽象化（SQLite/Postgres を `DATABASE_URL` で切替・`school` 先頭索引で水平分割可・失効時刻の UTC 統一）
- [x] データ編集の管理UI（`/admin`・`ADMIN_TOKEN` 保護・保存前に検証）
- [ ] 解析の時系列保存（現状は稼働中スナップショット）／本番 DB 運用（マイグレーション等）

## フェーズ4 — 全国グロース
- [x] 都道府県/地域ディレクトリ（トップを地域別にグルーピング・`/`・`/app/`）
- [x] データ鮮度管理（`data_updated`／学校ページ表示・ダッシュボード鮮度列・要更新バッジ・運用サイクル）
- [x] 各校メンテナ制度・運営ドキュメント（`docs/OPERATIONS.md`）
- [ ] SNS自動化の学校別テンプレ化（任意機能として分離・将来）

---

## デプロイ／本番運用
- [x] 本番起動構成（`Procfile`・`render.yaml`・`gunicorn run:app`・`docs/DEPLOY.md`）
- [x] 環境変数（`DATABASE_URL`／`ADMIN_TOKEN`／`PORT`）
- [ ] 実 Postgres での疎通確認（要 DB インスタンス）

---

### 完了の定義（フェーズ1の受け入れ基準・例）
- 新しい学校を **コードを一切変更せず** `schools/<slug>/` の追加だけで公開できる。
- NUST の検索結果が **旧 nust-room-search と一致**（曜日×時限×校舎で突合）。
- 予約・報告が学校間で衝突しない。
