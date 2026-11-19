# サブテーマ 1: 生成 AI 利用量の可視化ダッシュボード

`data/users.csv` と `data/ai_audit_logs.csv` を結合し、どの部署・ユーザーがどのモデルや機能をどれだけ使っているかを可視化する Web ダッシュボードを Antigravity で作成します。

## データ仕様

`ai_audit_logs.csv` には氏名や部署名が含まれず `user_id` のみが記録されているため、`users.csv` と `user_id` で結合して集計します。

### `data/users.csv`

ライセンス付与済みユーザー 25 名のマスタデータです。

| カラム名 | 型 | 内容 |
| :--- | :--- | :--- |
| `user_id` | 文字列 | ユーザー ID。`USR-0101` 〜 `USR-0125` |
| `user_email` | 文字列 | メールアドレス |
| `user_name` | 文字列 | 表示名 |
| `department` | 文字列 | 所属部署。`開発本部`、`AI統括部`、`データ統括部`、`情報システム部`、`営業本部`、`人事総務部` の 6 部署 |
| `job_role` | 文字列 | 職種 |

### `data/ai_audit_logs.csv`

生成 AI の利用ログ 100 件です。

| カラム名 | 型 | 内容 |
| :--- | :--- | :--- |
| `event_timestamp` | 日時文字列 | イベント発生日時 (UTC) |
| `log_id` | 文字列 | ログ ID。`LOG-202610-001` 〜 `LOG-202610-100` |
| `trace_id` | 文字列 | 32 桁 16 進数のトレース ID |
| `user_id` | 文字列 | 実行ユーザーの ID |
| `tool_surface` | 文字列 | 利用機能。`Gemini Enterprise Chat`、`Gemini Enterprise Search`、`BigQuery Data Agent`、`Antigravity` |
| `model_name` | 文字列 | 利用モデル。`gemini-3.8-flash`、`gemini-4-argon`、`claude-sonnet-5-5`、`claude-opus-5-5` |
| `input_tokens` | 整数 | 入力トークン数 |
| `output_tokens` | 整数 | 出力トークン数 |
| `latency_ms` | 整数 | 応答時間 (ミリ秒) |
| `prompt_text` | 文字列 | 入力プロンプト本文 |
| `connector_name` | 文字列 | 呼び出したコネクタ・ツール名 (`Google Drive`、`Confluence`、`Slack`、`Jira`、`Gmail`、`BigQuery`、`GitHub`、`none` 等) |
| `response_text` | 文字列 | モデルの応答テキスト |

## 要件

1. `data/users.csv` と `data/ai_audit_logs.csv` を `user_id` で結合して集計する。
2. 部署ごとのリクエスト件数、合計トークン数 (`input_tokens + output_tokens`)、平均レイテンシ、モデル別の利用内訳を比較できる。
3. ユーザーごとの利用量ランキングを表示し、部署やモデルで絞り込める。
4. ブラウザから確認できる Web ダッシュボード (ポート `8080`) として表示する。

## プロンプト例

リポジトリ直下 `ge-ai-handson/` で `agy` を起動し、以下を入力してベース画面を作成・起動します。

```text
theme1_usage_dashboard/README.md を読んで、data/users.csv と data/ai_audit_logs.csv を user_id で結合し、部署別およびユーザー別の生成AI利用量・合計トークン数・平均レイテンシ・モデル別内訳を可視化する Web ダッシュボードを theme1_usage_dashboard/app.py として作成してください。追加パッケージを使わずにポート 8080 (ホスト 0.0.0.0) でバックグラウンド起動して常駐させ、http://127.0.0.1:8080/ の応答確認まで行ってください。
```

## 拡張アイデア

ベース画面が動いたら、グループで相談して見たい指標や切り口を `agy` に指示します (改修後はブラウザを再読み込みするだけで反映を確認できます)。

| 切り口 | 内容例 |
| :--- | :--- |
| 未利用ユーザーの抽出 | `users.csv` の 25 名を基準に集計し、利用ログが 0 件のメンバーと部署別のアクティブ利用率を表示する |
| モデル別の仮想コスト試算 | 100 万トークンあたりの単価をモデルごとに仮置きし、高単価モデルの利用割合が高い部署やユーザーを可視化する |
| 利用機能の比較 | 部署ごとに `Gemini Enterprise Chat`、`BigQuery Data Agent`、`Antigravity` のどれが多く使われているか比較する |
| 日別の利用推移 | `event_timestamp` から日別のリクエスト数・トークン推移を集計する |

## 動作確認と共有タイムでの紹介ポイント

- Cloud Shell ターミナル上に表示された `http://localhost:8080` をクリックするか、ツールバー右上の **ウェブでプレビュー** アイコンから **ポート 8080 でプレビュー** を選択して画面を開きます。サブテーマ 2 ではポートを使わないため、ダッシュボードは停止せず起動したまま進められます。
- 補足: `agy` を終了した後に手動で起動する場合は、ターミナルで `python3 theme1_usage_dashboard/app.py` を実行します。
- 実装に詰まった場合は、サンプルコード (`samples/sample1_usage_dashboard/`) を参照できます。
- 共有タイムでは、データから見えた利用傾向やグループで追加した指標を紹介してください。
