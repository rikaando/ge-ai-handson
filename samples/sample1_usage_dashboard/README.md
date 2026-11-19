# サンプル 1: サブテーマ 1 の実装例 (利用量可視化ダッシュボード)

サブテーマ 1 (`theme1_usage_dashboard/app.py`) の Python 標準ライブラリによる参考実装と単体テストです。追加パッケージのインストールなしでそのまま実行できます。

## ファイル構成

| ファイル | 内容 |
| :--- | :--- |
| `app.py` | `users.csv` と `ai_audit_logs.csv` を `user_id` で結合し、部署別・モデル別・日別・ユーザー別の利用量、1人あたりトークン数、利用機能比率、平均レイテンシ、未利用ユーザーを可視化する Web ダッシュボード (ポート `8080`・自動リロード対応) および CLI |
| `test_app.py` | 部署別・モデル別・日別の集計件数、1人あたり指標、未利用ユーザー抽出、絞り込み条件を検証する単体テスト |

## 実行方法

以下のコマンドはすべてリポジトリ直下 `ge-ai-handson/` で実行します。

### Web ダッシュボードの起動

```bash
python3 samples/sample1_usage_dashboard/app.py --port 8080
```

Cloud Shell ターミナルに表示された `http://localhost:8080` をクリックするか、右上の **ウェブでプレビュー** から **ポート 8080 でプレビュー** を開いて確認します (ターミナルに集計サマリーのみを出力する場合は `--cli` を指定します)。

### 単体テストの実行

```bash
python3 -m unittest discover -s samples/sample1_usage_dashboard -p "test_*.py" -v
```

## Antigravity へのプロンプト例

リポジトリ直下 `ge-ai-handson/` で起動した `agy` に以下を入力すると、コードを変更せずに単体テストの実行や Web ダッシュボードの起動を行えます。

### 単体テストと Web ダッシュボードの起動

```text
コードは変更せず、samples/sample1_usage_dashboard/ の単体テストを実行したあと、samples/sample1_usage_dashboard/app.py をポート 8080 でバックグラウンド起動して常駐させ、http://127.0.0.1:8080/ の応答を確認してください (すでにポート 8080 で起動中のプロセスがある場合は停止してから起動してください)。
```

### CLI での集計サマリー表示

```text
コードは変更せず、python3 samples/sample1_usage_dashboard/app.py --cli を実行して部署別・ユーザー別の集計サマリーを表示してください。
```
