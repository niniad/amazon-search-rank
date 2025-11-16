# Amazon.co.jp ランク監視ツール (ローカル実行専用)

指定した ASIN / キーワードの組み合わせで Amazon.co.jp を検索し、スポンサー枠を除いた順位を 3 ページ目まで調査、結果を `@output` ディレクトリに CSV として保存します。GitHub Actions や GCS 連携は一切利用しません。

## 必要環境
- Python 3.11 以上
- Google Chrome (最新版)
- ChromeDriver は自動で取得するため、追加インストールは不要

## セットアップ
1. 依存パッケージをインストール
   ```bash
   pip install -r requirement.txt
   ```
2. `input.csv` を編集し、監視したい ASIN / 検索語を設定します。
   - 列構成: `ASIN,SEARCH TERM,ACTIVE`
   - `ACTIVE` を `yes` にすると監視対象、`no` にするとスキップ

## 使い方
```bash
python amazon_search_rank.py
```
- 実行すると Chromium のヘッドレスブラウザが自動起動し、キーワードごとに最大 3 ページまで巡回します。
- 結果は `@output/amazon-ranks-YYYYMMDD-HHMMSS.csv` というファイル名で保存されます。

## 出力ファイルの構成
| 列名 | 説明 |
| ---- | ---- |
| `timestamp` | 検索を実行した日時 (ローカルタイム) |
| `keyword` | 使用した検索語 |
| `asin` | 監視対象 ASIN |
| `status` | `found` または `not_found` |
| `page` | ASIN が見つかった検索結果ページ番号 (1〜3) |
| `position_on_page` | そのページ内での表示順 (スポンサーを除外してカウント) |
| `overall_position` | 1ページ目からの通算順位 (スポンサー除外) |

`not_found` 行は、指定の 3 ページ以内で当該 ASIN が見つからなかったことを示します。

## トラブルシューティング
- **Amazon で CAPTCHA やエラー画面が出る**: しばらく待って再実行するか、手動でブラウザを開いて人間によるアクセスでブロックを解除してください。
- **Chrome が起動しない／バージョン不一致**: いったん Chrome を最新化し、`webdriver-manager` が新しいドライバを取得できるようにしてください。
- **結果が空**: `input.csv` に `ACTIVE=yes` の行があるか、Amazon で該当キーワードがヒットするかを確認してください。
