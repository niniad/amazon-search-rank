# Amazon.co.jp ランク監視ツール (BS4-only / Server-Ready)

指定した ASIN / キーワードの組み合わせで Amazon.co.jp を検索し、検索順位（絶対順位およびオーガニック順位）を調査します。
Selenium を使用せず、`requests` と `BeautifulSoup` のみで動作するため、GitHub Actions や Google Cloud Run などのサーバーレス環境での定期実行に最適です。

## 特徴
- **高速・軽量**: ブラウザを起動しないため、高速に動作します。
- **サーバーレス対応**: Chrome のインストールが不要で、Python 環境だけで動作します。
- **詳細な順位データ**:
  - `rank`: ページ内の絶対順位（スポンサー枠を含む）
  - `organic_rank`: スポンサー枠を除いた自然検索順位
- **プロキシ対応**: `--proxy` オプションでプロキシ経由のアクセスが可能。

## 必要環境
- Python 3.11 以上
- `requests`
- `beautifulsoup4`

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
- デフォルトでは各キーワードにつき最大 **3ページ** まで検索します。
- ページ数を変更したい場合は `--pages` オプションを使用します（例: 5ページまで検索）。
  ```bash
  python amazon_search_rank.py --pages 5
  ```
- プロキシを使用する場合:
  ```bash
  python amazon_search_rank.py --proxy http://user:pass@host:port
  ```

## 順位取得ロジック
本ツールは以下のロジックで順位を算出しています。

1. **HTML取得**: `requests` ライブラリを使用して Amazon の検索結果ページ（HTML）を直接取得します。
2. **解析 (Parsing)**: `BeautifulSoup` を使用して HTML を解析し、`data-component-type='s-search-result'` 属性を持つ要素を検索結果アイテムとして抽出します。
3. **スポンサー判定**:
   - アイテム内のテキストに「スポンサー」または「Sponsored」が含まれるか、`aria-label` にそれらの文言が含まれる場合を「スポンサー枠」と判定します。
4. **順位計算**:
   - **rank (絶対順位)**: ページの上から順に数えた単純な出現順序です（スポンサー枠もカウント）。
   - **organic_rank (自然検索順位)**: スポンサー枠を除外してカウントした順位です。スポンサー枠の場合、この値は空になります。
   - 複数ページにまたがる場合、前のページのアイテム数を加算して累積順位を算出します。
5. **精度**: ブラウザで表示される内容と HTML ソースの構造に若干の差異がある場合があるため、実際の表示順位と ±1〜2 程度の誤差が生じることがあります（許容範囲として設計）。

## 出力ファイルの構成
結果は `@output` ディレクトリに CSV として保存されます。

| 列名 | 説明 |
| ---- | ---- |
| `timestamp` | 実行日時 |
| `keyword` | 検索キーワード |
| `asin` | 対象 ASIN |
| `type` | `Organic` (自然検索) または `Sponsored Product` (広告) |
| `page` | 発見されたページ番号 |
| `rank` | 絶対順位 (広告含む) |
| `organic_rank` | 自然検索順位 (広告除く) |

## トラブルシューティング
- **結果が空 (No results found)**:
  - Amazon 側の仕様変更により HTML 構造が変わった可能性があります。
  - アクセス過多によりブロックされている可能性があります。時間を空けるか、プロキシの使用を検討してください。
