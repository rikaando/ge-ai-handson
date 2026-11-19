# Gemini Enterprise & Antigravity ハンズオン

<walkthrough-tutorial-duration duration="60"></walkthrough-tutorial-duration>

生成 AI 利用ログ `data/ai_audit_logs.csv` とユーザーマスタ `data/users.csv` を使い、以下の 2 パートを進めます。

- パート 1: BigQuery の対話型分析エージェント作成と Gemini Enterprise 連携
- パート 2: Antigravity を使った利用量可視化ダッシュボードとクレジットカード番号検出ツールの作成

右下の **開始** をクリックしてください。

## Step 1: 環境変数の設定

他の参加者と BigQuery データセット名やエージェント名が重複しないよう、ログイン中のアカウントから識別子 `USER_ID` を設定します。

```bash
[ -f ./data/users.csv ] || cd "${HOME}/ge-ai-handson" 2>/dev/null || true
export GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project 2>/dev/null)
export USER_ID=$(gcloud config get-value account 2>/dev/null | cut -d'@' -f1 | tr '[:upper:].-' '[:lower:]__' | tr -cd 'a-z0-9_')
export USER_ID="${USER_ID:-user01}"
export HANDSON_DIR=$(pwd)
printf 'export %s="%s"\n' GOOGLE_CLOUD_PROJECT "${GOOGLE_CLOUD_PROJECT}" USER_ID "${USER_ID}" HANDSON_DIR "${HANDSON_DIR}" > "${HOME}/.ge_handson_env"
echo "PROJECT_ID : ${GOOGLE_CLOUD_PROJECT:-(unset)}"
echo "BQ_DATASET : ge_handson_${USER_ID}"
echo "BQ_AGENT   : audit_analyzer_${USER_ID}"
```

`PROJECT_ID` が `(unset)` と表示された場合は `gcloud config set project <プロジェクトID>` でプロジェクトを設定してから、上記のコマンドを再実行してください。出力された `BQ_DATASET` と `BQ_AGENT` の値を次のステップで使用します。確認できたら **次へ** をクリックします。

## Step 2: パート 1 BigQuery 対話型分析エージェントの作成

BigQuery データセットを作成して `users` と `ai_audit_logs` の 2 テーブルを登録し、対話型分析エージェントを公開します。

1. 以下のコマンドを実行してデータセットと 2 つのテーブルを作成します。

```bash
source "${HOME}/.ge_handson_env"
cd "${HANDSON_DIR}"
gcloud config set project "${GOOGLE_CLOUD_PROJECT}" --quiet
bq --location=US mk -d -f "${GOOGLE_CLOUD_PROJECT}:ge_handson_${USER_ID}"
bq load --replace --source_format=CSV --skip_leading_rows=1 "${GOOGLE_CLOUD_PROJECT}:ge_handson_${USER_ID}.users" ./data/users.csv ./data/users_schema.json
bq load --replace --source_format=CSV --skip_leading_rows=1 "${GOOGLE_CLOUD_PROJECT}:ge_handson_${USER_ID}.ai_audit_logs" ./data/ai_audit_logs.csv ./data/ai_audit_schema.json
```

2. ブラウザの別タブで [BigQuery コンソール](https://console.cloud.google.com/bigquery?hl=ja) を開き、左メニューの **エージェント** > **+ 新しいエージェント** をクリックします。
3. エージェント名に Step 1 で出力された `audit_analyzer_<USER_ID>`、リージョンに `US` を指定します。
4. ナレッジソースの **ソースの追加** をクリックし、作成したデータセット `ge_handson_<USER_ID>` 内の `users` と `ai_audit_logs` の **2 つのテーブル** を選択して追加します。
5. 手順欄に以下をコピーして貼り付けます。

```text
社内の生成AI利用状況を分析するデータアナリストとして回答してください。
- ai_audit_logs には user_id のみが記録されているため、部署名 department や氏名 user_name で集計する際は users テーブルと user_id で結合してください。
- 合計トークン数は input_tokens + output_tokens で算出し、比較時は集計表と棒グラフを出力してください。
- クレジットカード番号の混入状況などを聞かれた際は、該当ログの件数と発生部署を集計して報告してください。
```

6. 右上の **保存** をクリックし、続けて **公開** > **Publish agent** をクリックします。
7. 共有ダイアログが開いたら **プリンシパルを追加** をクリックし、共有したいユーザーや Google グループのメールアドレスを入力し、ロール **Gemini データ分析データ エージェント ユーザー** (`roles/geminidataanalytics.dataAgentUser`) を付与して保存します。
8. 再度 **公開** を開き、**A2A 経由での統合** に表示される **JSON をコピー** をクリックします。

JSON をコピーしたら **次へ** をクリックします。

## Step 3: パート 1 Gemini Enterprise への登録と動作確認

BigQuery で公開した対話型分析エージェントを Gemini Enterprise に接続し、チャット画面から自然言語で質問して動作を確認します。

1. [Gemini Enterprise コンソール](https://console.cloud.google.com/gemini-enterprise/apps?hl=ja) で対象アプリを開き、左メニューの **エージェント** > **+ エージェントを追加** をクリックします。
2. **A2A によるカスタム エージェント** を選択し、Step 2 でコピーした JSON を貼り付けて次へ進みます。
3. 認可画面で **Google が管理するデフォルトの認証情報** を選択して登録を完了します。
4. 追加したエージェントの詳細画面で **ユーザー権限** タブを開き、**ユーザーを追加** から自分や共有したいハンズオン参加者のメールアドレスを入力し、**エージェント ユーザー** (`roles/discoveryengine.agentUser`) を付与します。
5. 左メニューの **概要** からアプリの URL をクリックして Gemini Enterprise の Web アプリ画面へ移動します (すでに開いている場合は再読み込みします)。
6. Web アプリの左メニュー **エージェント** から追加したエージェントを選択して以下の質問を試します。初回利用時に `エージェントに次の場所へのアクセスを追加で承認する必要があります。` と表示されたら、**承認** をクリックして自分のアカウントを選択します。

```text
部署ごとのリクエスト件数と合計トークン数を集計して棒グラフで比較して
```

```text
users テーブルの25名のうち、まだ1回も生成AIを使っていないメンバーの部署名と名前を教えて
```

```text
prompt_text に14桁または16桁のクレジットカード番号らしき数字が含まれるログ件数を部署別に集計して
```

確認できたら **次へ** をクリックします。

## Step 4: パート 2 Antigravity の起動

Cloud Shell の `agy` コマンドで Antigravity を起動します。本ハンズオンでは Gemini モデルのみを使用します。

1. 以下のコマンドでリポジトリ直下に移動し、`agy` を起動します。

```bash
[ -f "${HOME}/.ge_handson_env" ] && . "${HOME}/.ge_handson_env"
cd "${HANDSON_DIR:-${HOME}/ge-ai-handson}"
agy
```

2. 初回サインイン画面では以下の順に選択します。
   - `Select login method:` で **2. Use a Google Cloud project** を選択します。続けて認証画面が表示された場合は **1. Continue with Google Cloud** を選び、表示された URL をブラウザで開いて認証コードを貼り付けます。
   - `Select billing model:` で **1. Subscriptions** を選択します。
   - `Select available subscription:` で対象の **Gemini Enterprise** サブスクリプションを選択します (一覧に表示されない場合は `Enter a Google Cloud project` から対象プロジェクト ID と `global` を指定します)。続けてフォルダの信頼確認が表示されたら `Yes, I trust this folder` を選択します。

準備ができたら **次へ** をクリックします。

## Step 5: サブテーマ 1 利用量可視化ダッシュボード

部署別・ユーザー別の生成 AI 利用量を可視化する Web ダッシュボードを作成します。

1. 以下の手順書を開き、プロンプト例を使ってダッシュボードの作成とポート `8080` でのバックグラウンド起動を Antigravity に指示します。

<walkthrough-editor-open-file filePath="theme1_usage_dashboard/README.md">theme1_usage_dashboard/README.md を開く</walkthrough-editor-open-file>

2. ターミナルに表示された `http://localhost:8080` をクリックするか、Cloud Shell ツールバー右上の <walkthrough-web-preview-icon></walkthrough-web-preview-icon> <walkthrough-spotlight-pointer spotlightId="cloud-shell-web-preview-button" target="cloudshell">ウェブでプレビュー</walkthrough-spotlight-pointer> から **ポート 8080 でプレビュー** を選択して画面を確認します (上の **ウェブでプレビュー** をクリックするとツールバー上のボタン位置がハイライトされます)。
3. 追加したい指標やフィルタをグループで相談して Antigravity に指示し、ブラウザを再読み込みして反映を確認します。
4. ダッシュボードは停止せず起動したまま **次へ** をクリックします (後の共有タイムでもそのまま画面を表示できます)。

## Step 6: サブテーマ 2 クレジットカード番号の検出

`data/ai_audit_logs.csv` の `prompt_text` から 14 桁・16 桁のクレジットカード番号をルールベースで検出し、監査レポートを標準出力に表示する Python ツールを作成します。

1. 以下の手順書を開き、プロンプト例を使って Antigravity に検出スクリプトと単体テストの作成・実行を指示します。

<walkthrough-editor-open-file filePath="theme2_credit_card_audit/README.md">theme2_credit_card_audit/README.md を開く</walkthrough-editor-open-file>

2. 単体テストの結果と標準出力の監査レポートを見て、注文番号、法人番号、バッチジョブ ID、18 桁の追跡番号などを誤検知せず、カード番号を含むログのみを抽出できているか確認します。
3. グループで相談して任意のテキスト判定オプションや集計切り口を追加し、出力結果を確認できたら **次へ** をクリックします。

## Step 7: サンプルコードと片付け

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>

`samples/` 配下にサブテーマ 1・2 の参考実装と、Cloud Run へのデプロイ資材を格納しています。

<walkthrough-editor-open-file filePath="samples/sample1_usage_dashboard/README.md">samples/sample1_usage_dashboard/README.md を開く</walkthrough-editor-open-file>

<walkthrough-editor-open-file filePath="samples/sample2_credit_card_audit/README.md">samples/sample2_credit_card_audit/README.md を開く</walkthrough-editor-open-file>

<walkthrough-editor-open-file filePath="samples/sample3_cloud_run_a2a/README.md">samples/sample3_cloud_run_a2a/README.md を開く</walkthrough-editor-open-file>

監査エージェントを Cloud Run へデプロイして Gemini Enterprise に接続する場合は、`samples/sample3_cloud_run_a2a/README.md` のプロンプト例を `agy` に入力してサンドボックス外での実行を承認するか、Cloud Shell 上部の `+` アイコンで開いた通常のターミナルタブで以下を実行したあと、出力された `agent_card.json` を Gemini Enterprise コンソールに登録します。

```bash
[ -f "${HOME}/.ge_handson_env" ] && . "${HOME}/.ge_handson_env"
cd "${HANDSON_DIR:-${HOME}/ge-ai-handson}"
bash ./samples/sample3_cloud_run_a2a/deploy_a2a.sh
```

Step 2 で作成した BigQuery データセットを削除する場合は以下を実行します。

```bash
source "${HOME}/.ge_handson_env"
bq rm -r -f -d "${GOOGLE_CLOUD_PROJECT}:ge_handson_${USER_ID}"
```
