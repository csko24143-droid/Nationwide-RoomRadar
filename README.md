# Nationwide RoomRadar

**全国の学校で使える「空き教室リアルタイム検索」プラットフォーム。**

学生が曜日・時限・校舎から「いま空いている教室」を即座に探せる RoomRadar を、
単一大学向け（[`nust-room-search`](https://github.com/csko24143-droid/nust-room-search)）から
**複数校をホストできるマルチテナント構成** へ発展させるプロジェクト。

> 現在のステータス: **フェーズ1（テナント化MVP）着手**。
> 学校非依存の空き判定エンジンと設定/データのローダを実装し、
> 日大理工（NUST）を最初の実データテナントとして移行済み（旧実装と全コマ一致を検証）。

---

## コンセプト

- **学校追加はデータ追加だけ**：新しい学校は `schools/<slug>/` に
  設定（`config.yml`）と時間割（`schedule.csv`）を置くだけ。コード変更不要。
- **静的コア＋薄い動的レイヤ**：空き判定は時間割＋現在時刻だけで決まる純粋計算。
  仮予約・報告だけ小さなバックエンドに集約 → **学校が増えてもサーバ負荷はほぼ増えない**。
- **非公式・情報共有**：大学公式の予約ではなく、学生同士の助け合いツール。

## クイックスタート

```bash
pip install -r requirements.txt

# テスト（コアエンジン。pytest 不要・標準ライブラリの unittest）
python -m unittest discover -s tests -v

# Web アプリ（全国トップ / 各校検索）を起動
python run.py            # → http://localhost:10000
#   /                    全国トップ（学校一覧）
#   /s/nust              日大理工の空き教室検索
#   /s/example-tech      サンプル校（構成の異なる2校目）
```

## プロジェクト構成

```
roomradar/            学校非依存のコア（このコードは学校を知らない）
  config.py           config.yml / index.json のローダ＋検証
  terms.py            日付→有効な学期（純粋関数）
  availability.py     空き判定エンジン（使用中集合の差集合・純粋関数）
  data.py             schedule.csv / classrooms.csv のローダ
  school.py           設定＋データを束ねた 1 校分のモデル
  webapp.py           最小 Flask アプリ（/ と /s/<slug>）
schools/              テナント（学校）データ。ここを足すだけで学校が増える
  index.json          全国レジストリ
  nust/               日大理工（実データ。config + schedule.csv + classrooms.csv）
  example-tech/       マルチテナント実証用サンプル校
scripts/
  export_nust.py      旧DB→CSV 移行＋旧実装との一致検証（DESIGN §13）
tests/                unittest（terms / availability / config / multi-tenant）
docs/                 設計書一式
```

## 学校を追加するには

1. `schools/<slug>/config.yml` を作成（雛形: [`docs/examples/nust.config.yml`](docs/examples/nust.config.yml)）。
2. `schools/<slug>/schedule.csv`（時間割）を用意（仕様: [`docs/data-import-format.md`](docs/data-import-format.md)）。
   常時空きの教室も出したい場合は `classrooms.csv` も置く（任意）。
3. `schools/index.json` にエントリを追加。
4. `python -m unittest` が通れば OK。**コードの変更は不要。**

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [`docs/DESIGN.md`](docs/DESIGN.md) | **設計書（本体）**。現状分析・アーキテクチャ・データモデル・移行計画 |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | フェーズ別の実装チェックリスト |
| [`docs/data-import-format.md`](docs/data-import-format.md) | 時間割CSV/Excel の仕様とテンプレ |
| [`docs/examples/`](docs/examples/) | 学校設定・時間割の記入例 |

## いまの達成状況（フェーズ1）

- [x] 設定/レジストリのローダ（`config.yml` / `index.json`）
- [x] 空き判定エンジンの学校非依存化（校舎別 if 分岐を撤去）
- [x] 時限・学期・曜日・校舎・色・学校名を config から注入（ハードコード排除）
- [x] 学期判定の汎用化（年跨ぎ対応の純粋関数）
- [x] NUST 移行：DB→CSV、**旧実装と全 36 コマで一致を検証**
- [x] 全国トップ＋各校検索の最小 Web アプリ
- [ ] 予約・報告 API の `school` スコープ化（DESIGN §5.4）
- [ ] フロント統合・クライアント計算化（フェーズ2）

残タスクは [`docs/ROADMAP.md`](docs/ROADMAP.md) を参照。
