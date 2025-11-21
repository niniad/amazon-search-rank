# Amazon Search Rank Tracker

Amazon.co.jpで商品の検索順位を追跡するツールです。Selenium を使用して正確な広告検出とランキングを実現します。

## 機能

- **正確な広告検出**: Sponsored（広告）とOrganic（自然検索）を自動判定
- **複数ページ対応**: 最大3ページまで自動検索
- **スクリーンショット機能**: 検証用の全ページスクリーンショット撮影
- **Cloud Run対応**: Google Cloud Run Jobsでの実行に対応

## 必要要件

- Python 3.9以上
- Chrome ブラウザ（ローカル実行時）

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 入力ファイルの準備

`input.csv` を以下の形式で作成：

```csv
ASIN,SEARCH TERM,ACTIVE
B0DBSF1CZ6,お食事エプロン,yes
B0DBSB6XY9,お食事エプロン,yes
B0D88XNCHG,食事用エプロン,yes
```

- **ASIN**: 追跡する商品のASIN
- **SEARCH TERM**: 検索キーワード
- **ACTIVE**: yes/no（追跡するかどうか）

## 使用方法

### ローカル実行

```bash
# 基本実行
python amazon_search_rank.py

# スクリーンショット付き実行
python amazon_search_rank.py --screenshot
```

### 出力

実行後、`@output` ディレクトリに以下が生成されます：

- `amazon_ranks_YYYYMMDD_HHMMSS.csv`: ランキング結果
- `images/`: スクリーンショット（--screenshot オプション使用時）

#### 出力CSV形式

```csv
timestamp,keyword,asin,type,page,rank,organic_rank
2025-11-22T00:13:48,お食事エプロン,B0DBSF1CZ6,Sponsored,1,7,
2025-11-22T00:13:49,お食事エプロン,B0DBSB6XY9,Organic,1,44,20
```

- **timestamp**: 検索実行日時
- **keyword**: 検索キーワード
- **asin**: 商品ASIN
- **type**: Sponsored（広告）/ Organic（自然検索）
- **page**: 見つかったページ番号
- **rank**: 全体順位（広告含む）
- **organic_rank**: 自然検索順位（Organicの場合のみ）

## Cloud Run へのデプロイ

### 1. GCPプロジェクトの設定

```powershell
# プロジェクトIDを設定
$PROJECT_ID = "your-project-id"
gcloud config set project $PROJECT_ID
```

### 2. デプロイスクリプトの実行

```powershell
.\deploy.ps1
```

または手動でデプロイ：

```bash
# Artifact Registryにイメージをビルド＆プッシュ
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/$PROJECT_ID/amazon-rank/amazon-rank-scraper

# Cloud Run Jobを作成
gcloud run jobs create amazon-rank-job \
  --image asia-northeast1-docker.pkg.dev/$PROJECT_ID/amazon-rank/amazon-rank-scraper \
  --region asia-northeast1 \
  --memory 2Gi \
  --cpu 1 \
  --max-retries 1 \
  --task-timeout 30m
```

### 3. Cloud Runでの実行

```bash
gcloud run jobs execute amazon-rank-job --region asia-northeast1
```

## プロジェクト構成

```
amazon-search-rank/
├── amazon_search_rank.py   # メインスクリプト
├── cloud_runner.py          # Cloud Run用エントリーポイント
├── input.csv                # 入力ファイル
├── requirements.txt         # 依存パッケージ
├── Dockerfile               # Cloud Run用
├── deploy.ps1               # デプロイスクリプト
├── @output/                 # 出力ディレクトリ
│   ├── amazon_ranks_*.csv
│   └── images/
└── archive/                 # 過去のファイル
```

## 広告検出の仕組み

このツールは3つの方法で広告を検出します：

1. **属性チェック**: `data-component-type` 属性に "sponsored" が含まれるか確認
2. **バッジチェック**: 要素内の "スポンサー" バッジを検出
3. **近接検出**: 商品要素の200px以内に "スポンサー" ラベルがあるか確認

## トラブルシューティング

### Chrome Driver エラー

```bash
# webdriver-manager が自動的にChromeDriverをダウンロードします
# エラーが出る場合は手動でインストール：
pip install --upgrade webdriver-manager
```

### タイムアウトエラー

`amazon_search_rank.py` の `SPONSORED_PROXIMITY_THRESHOLD` や待機時間を調整してください。

## ライセンス

MIT License

## 注意事項

- Amazon.co.jpの利用規約を遵守してください
- 過度なリクエストはIPアドレスがブロックされる可能性があります
- 商用利用の場合は適切な間隔でリクエストを行ってください
