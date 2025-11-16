## Amazon.co.jp ランク監視ツール

特定のキーワードで Amazon.co.jp を検索し、監視したい ASIN が何位に表示されるかを 1 時間ごとに記録して Google Cloud Storage (GCS) に CSV として保存します。IPRoyal プロキシ経由で Selenium + Chrome を起動し、スポンサー枠を除外した順位を取得します。

---

## 動作概要

1. GitHub Actions が毎時 0 分に起動。
2. `amazon_search_rank.py` がキーワードごとに Amazon.co.jp を検索。
3. **常に 3 ページ目まで** Selenium で巡回（1・2 ページでヒットしても 3 ページ目まで確認）。
4. 広告 (`placement=sponsored`) と通常表示 (`placement=organic`) をそれぞれ記録し、`timestamp, keyword, asin, placement, status, page, position_on_page, overall_position` を含む CSV を生成。
5. 生成した CSV を `gs://<GCS_BUCKET_NAME>/<GCS_PREFIX>/...` へアップロード。

---

## 必要な Secrets（GitHub リポジトリ Settings > Secrets and variables > Actions）

以下 6 項目すべてをチェック ✓ してからワークフローを有効化してください。

- [ ] `GCP_SA_KEY`：GCS へ書き込み権限を持つサービスアカウントの JSON
- [ ] `GCS_BUCKET_NAME`：結果を保存するバケット名
- [ ] `IPROYAL_HOST`
- [ ] `IPROYAL_PORT`
- [ ] `IPROYAL_USERNAME`
- [ ] `IPROYAL_PASSWORD`

Secrets は Actions から自動的に環境変数として読み込まれるため、コード側で追加設定は不要です。

---

## キーワード / ASIN の編集方法

フォーク元と同様に `input.csv` を編集します。列構成は `ASIN,SEARCH TERM,ACTIVE,DETAILS` の 4 つです。`ACTIVE` を `yes` にすると監視対象、`no` にするとスキップされます。例:

```
ASIN,SEARCH TERM,ACTIVE,DETAILS
B0D894LS44,お食事エプロン,yes,
B0D89H2L67,食事用エプロン,yes,
```

ポイント:

1. 1 行につき 1 つの ASIN/キーワードの組み合わせを記入します。
2. 同じ ASIN を別のキーワードで監視したい場合は行を追加してください。
3. CSV 内に有効な行が 1 件もない場合、スクリプトはエラーで終了します。

必要に応じて `INPUT_CSV` 環境変数を設定すると別ファイルを参照できます（既定値は `input.csv`）。`MAX_PAGES`（既定値 3）や `GCS_PREFIX` などその他の環境変数は引き続き `.github/workflows/main.yml` の `env` セクションで変更できます。旧フォーク元のスクリプトは `@/archive` に移動済みで、GitHub Actions／新スクリプトから参照されません。

---

## ローカルでの動作確認

1. Python 3.11 以上をインストール。
2. 依存ライブラリを導入。
   ```bash
   pip install -r requirement.txt
   ```
3. 以下の環境変数をローカルにも設定（例として `export` を利用）。
   ```bash
   export GCP_SA_KEY='{"type": "...", ... }'
   export GCS_BUCKET_NAME="your-bucket"
   export IPROYAL_HOST="proxy.example.com"
   export IPROYAL_PORT="1234"
   export IPROYAL_USERNAME="user"
   export IPROYAL_PASSWORD="pass"
   export INPUT_CSV="input.csv"   # 省略時は input.csv
   ```
4. スクリプトを実行。
   ```bash
   python amazon_search_rank.py
   ```
5. 完了するとターミナルに GCS へアップロードしたパスが表示されます。

---

## 結果の確認方法

1. GCS コンソールを開き、`GCS_BUCKET_NAME` で指定したバケットを表示。
2. `GCS_PREFIX` で指定したフォルダ（既定: `amazon-search-rank/hourly`）を開く。
3. `amazon-ranks-YYYYMMDDTHHMMSSZ.csv` 形式のファイルをダウンロード。
4. CSV を開くと、各行に以下が記録されています（広告・通常表示それぞれで 1 行ずつ出力）。
   - `timestamp`: 実際の計測開始時刻 (UTC)
   - `run_date`: cron 実行時刻を切り捨てた日付（例: `2025-01-01`）
   - `run_time`: cron 実行時刻を切り捨てた時刻（常に `HH:MM` で 00 分固定）
   - `keyword`: 検索語
   - `asin`: 追跡対象 ASIN
   - `placement`: `sponsored`（広告）または `organic`（通常）
   - `status`: `found` / `not_found`
   - `page`: 該当表示が見つかったページ（1～3）。未発見なら空欄。
   - `position_on_page`: そのページ内での表示順。未発見なら空欄。
   - `overall_position`: 1 ページ目から通算した表示順（同じ `placement` 内でカウント）。未発見なら空欄。

`status=not_found` の行は、指定した 3 ページ内で該当の表示が確認できなかったことを意味します。

---

## GitHub Actions の動作

- ワークフロー定義: `.github/workflows/main.yml`
- スケジュール: `cron: "0 * * * *"`（毎時 0 分）
- 手動実行: GitHub リポジトリの Actions タブから `Run workflow` を押下
- 失敗時: Actions のログに Selenium のスクリーンショット出力はありませんが、エラー内容はログに残ります。

---

## トラブルシューティング

| 事象 | 確認ポイント |
| --- | --- |
| `input.csv に有効な ASIN / キーワードの行がありません` | CSV に `ACTIVE=yes` の行があるか確認 |
| `GCP_SA_KEY が正しい JSON 形式ではありません` | Secrets に余計な改行や文字が混ざっていないか確認 |
| `検索結果の読み込みに失敗` | Amazon 側のブロックやネットワーク揺らぎ。次の自動実行で復旧するか観察 |
| Selenium が要素を見つけられない | Amazon UI 変更の可能性。`RESULTS_SELECTOR` などのセレクタを更新 |

---

## 参考コマンド

```bash
# 依存パッケージの更新
pip install --upgrade -r requirement.txt

# ワークフローで使うスクリプトの直接実行
python amazon_search_rank.py
```
