# デプロイ手順

RoomRadar の Flask アプリ 1 つで、すべてが動きます:
`/`（サーバ描画）・`/app/`（静的・クライアント計算）・`/api/...`（予約・報告）・
`/dashboard`（運用）・`/admin`（管理UI）。**まずはこのアプリをデプロイするのが最短**です。

## 環境変数

| 変数 | 既定 | 用途 |
|---|---|---|
| `PORT` | `10000` | 待受ポート（多くの PaaS が自動設定） |
| `DATABASE_URL` | 未設定＝SQLite `live.db` | `postgresql://…` で Postgres（要 `psycopg`）。予約・報告の永続化に推奨 |
| `ADMIN_TOKEN` | 未設定＝管理UI無効 | `/admin` のアクセストークン |

> SQLite を一時ディスク（無料 PaaS など）で使うと、再デプロイで予約・報告は消えます。
> もともと時限終了で自動失効する揮発データなので実害は小さいですが、永続化したい場合は
> `DATABASE_URL` に Postgres を設定し、`requirements.txt` の `psycopg` を有効化してください。
> 学校データ（`schools/`）は git 管理なので消えません。

## 1. Render（ブループリント）

リポジトリ直下の [`render.yaml`](../render.yaml) を読み込みます。

1. https://dashboard.render.com → New → Blueprint → このリポジトリを選択。
2. `ADMIN_TOKEN` は自動生成されます（永続化したい場合は Postgres を作成し `DATABASE_URL` を設定）。
3. デプロイ後、`https://<service>.onrender.com/` で公開。

ビルド: `pip install -r requirements.txt && python scripts/build.py`
起動: `gunicorn run:app --bind 0.0.0.0:$PORT`

## 2. Railway / Fly.io / Heroku 系

[`Procfile`](../Procfile)（`web: gunicorn run:app …`）を使います。

```bash
pip install -r requirements.txt
python scripts/build.py        # dist/ を生成（/app・/dashboard で使用）
gunicorn run:app --bind 0.0.0.0:$PORT
```

`DATABASE_URL` / `ADMIN_TOKEN` をプラットフォームの環境変数に設定してください。

## 3. GitHub Pages（静的のみ・予約は別バックエンド）

検索だけなら、`web/` と `dist/` を静的ホスティングするだけで動きます（空き計算はブラウザ側）。

```bash
python scripts/build.py
# web/ と dist/ を公開（例: gh-pages ブランチ、または docs/ 公開設定）
```

- 予約・報告・管理UI はバックエンドが必要です。別途上記 1/2 で Flask を立て、
  静的ページ側で `window.ROOMRADAR_API`（と必要なら `window.ROOMRADAR_DIST`）を
  そのURLへ向けてください（`web/*.html` 読み込み前に `<script>` で定義）。

## デプロイ前チェック（CI と同じ）

```bash
python scripts/validate.py                 # 学校データ検証
python scripts/build.py                    # 配信用 JSON
python -m unittest discover -s tests       # テスト
```
