# 時間割・教室データ フォーマット仕様

新しい学校を追加するときの **データの形式** を定義する。
（全体設計は [`DESIGN.md`](./DESIGN.md) §5・§7 を参照）

学校ごとに以下を `schools/<slug>/` に置く。

| ファイル | 必須 | 内容 |
|---|---|---|
| `config.yml` | ◯ | 学校設定（[記入例](./examples/nust.config.yml)） |
| `schedule.csv` | ◯ | 時間割（授業が入っているコマの一覧） |
| `classrooms.csv` | △ | 教室マスタ。無い場合は `schedule.csv` から自動生成 |

> Excel（.xlsx）で作っても可。取り込み時に CSV へ変換する。**1行目はヘッダ（英語列名・固定）**。

---

## 1. `schedule.csv`（時間割）

「**その曜日・時限に授業が入っている**」コマを1行ずつ列挙する。
RoomRadar はここに**無い**教室を「空き」と判定する。

| 列 | 必須 | 型/例 | 説明 |
|---|---|---|---|
| `department` | △ | `物理学科` | 学科・コース（表示/集計用。空でも可） |
| `term` | ◯ | `前期` | `config.yml` の `terms[].id` のいずれか |
| `day` | ◯ | `月` | `config.yml` の `days` のいずれか |
| `period` | ◯ | `2` | `config.yml` の `periods[].no` のいずれか（整数） |
| `room` | ◯ | `123` | 教室名（表示文字列。表記を統一すること） |
| `building` | ◯ | `タワースコラ` | `config.yml` の `buildings[].name` と**完全一致** |
| `course` | △ | `力学I` | 科目名（表示用。空でも可） |

例:
```csv
department,term,day,period,room,building,course
物理学科,前期,月,2,123,タワースコラ,力学I
機械工学科,前期,火,1,M201,船橋校舎,材料力学
```
テンプレ: [`examples/schedule.sample.csv`](./examples/schedule.sample.csv)

---

## 2. `classrooms.csv`（教室マスタ・任意）

「学校に存在する**全教室**」の一覧。これがあると、時間割に一度も登場しない
（＝常に空き）教室も候補に含められる。無ければ `schedule.csv` の room から自動生成。

| 列 | 必須 | 例 | 説明 |
|---|---|---|---|
| `room` | ◯ | `123` | 教室名（`schedule.csv` の room と表記一致） |
| `building` | ◯ | `タワースコラ` | `config.yml` の `buildings[].name` と一致 |

---

## 3. 検証ルール（取り込み時に自動チェック）

`scripts/validate.py`（フェーズ2で実装予定）が以下を確認する:

1. ヘッダ列が規定どおり揃っている。
2. `term` / `day` / `period` が `config.yml` の定義集合に含まれる。
3. `building` が `config.yml` の `buildings[].name` のいずれかに一致（表記ゆれ検出）。
4. `period` が整数で `periods[].no` に存在。
5. 同一 `(term, day, period, room)` の重複行を検出（警告）。
6. `room` の表記ゆれ（全角/半角・前後空白）を正規化または警告。

検証を通ったデータだけが配信用 JSON（`schedule.<slug>.json`）にビルドされる。

---

## 4. 提出方法

- **GitHub が使える人**: `schools/<slug>/` を追加して Pull Request。
- **苦手な人**: Issue テンプレ「学校追加リクエスト」、または配布スプレッドシート/Google フォームに記入
  → メンテナが CSV 化してコミット（フェーズ2で整備）。

詳細な貢献手順は今後 `CONTRIBUTING.md` に集約する。
