# コントリビューションガイド — 学校を追加する

Nationwide RoomRadar は **データを追加するだけで学校が増える** 設計です（コード変更不要）。
自分の学校を載せたい人向けの手順をまとめます。

## 仕組み（前提）

- 学校固有の情報（校舎・時限・学期・曜日・色・学校名）はすべて
  `schools/<slug>/config.yml` と CSV に書かれています。
- 空き判定エンジン（`roomradar/`）は学校に依存しません。
- データ仕様は [`docs/data-import-format.md`](docs/data-import-format.md)、
  全体設計は [`docs/DESIGN.md`](docs/DESIGN.md) を参照。

---

## A. GitHub が使える人（Pull Request）

1. `schools/<slug>/` を作成（`<slug>` は英小文字・ハイフンの一意ID。例: `nust`）。
2. 次の3ファイルを置く:
   - `config.yml` … 学校設定。雛形 → [`docs/examples/nust.config.yml`](docs/examples/nust.config.yml)
   - `schedule.csv` … 時間割（授業が入っているコマの一覧）
   - `classrooms.csv` … 教室マスタ（任意。無ければ時間割から自動生成）
3. `schools/index.json` にレジストリのエントリを追加。
4. ローカルで検証・ビルド・テストが通ることを確認:
   ```bash
   pip install -r requirements.txt
   python scripts/validate.py --slug <slug>   # データ形式チェック
   python scripts/build.py                     # 配信用JSONの生成
   python -m unittest discover -s tests        # テスト
   ```
5. Pull Request を作成。CI（`.github/workflows/ci.yml`）が検証・ビルド・テストを自動実行します。

### よくある検証エラー
- `building '…' が config の建物名と不一致` → `schedule.csv` の `building` 列は
  `config.yml` の `buildings[].name` と **完全一致** させる（表記ゆれに注意）。
- `period '…' は config の periods 外` → `period` は整数で、`config.yml` の
  `periods[].period` に存在する番号にする。
- `term / day` も同様に `config.yml` の定義集合に合わせる。

---

## B. GitHub が苦手な人（Issue で依頼）

[Issue を作成](../../issues/new/choose) → **「学校の追加リクエスト」** テンプレートに沿って
学校名・校舎・時限・時間割の入手元などを記入してください。メンテナが CSV 化して取り込みます。

---

## データの扱いについて（お願い）

- 時間割の **入手元の利用規約・再配布可否** を確認してください（公式・シラバス等）。
  スクレイピングは権利・形式変更リスクが高いため推奨しません（[DESIGN §15](docs/DESIGN.md)）。
- 本サービスは **大学公式の予約ではなく**、学生同士の情報共有です。
- 個人が特定される情報（実名など）は時間割データに含めないでください。
