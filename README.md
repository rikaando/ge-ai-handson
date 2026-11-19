# Gemini Enterprise & Antigravity ハンズオン

生成 AI 利用ログ `data/ai_audit_logs.csv` とユーザーマスタ `data/users.csv` を使い、BigQuery の対話型分析エージェントの作成と Antigravity によるアプリケーション開発を体験するハンズオン資材です。

## セットアップ

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://console.cloud.google.com/cloudshell/open?cloudshell_git_repo=https://github.com/rikaando/ge-ai-handson&cloudshell_tutorial=tutorial.md)

ターミナルから取得する場合は以下を実行します。

```bash
git clone https://github.com/rikaando/ge-ai-handson.git
cd ge-ai-handson
```

Cloud Shell の右ペインで手順ガイドを開く場合は、続けて以下を実行します。

```bash
cloudshell launch-tutorial tutorial.md
```

## ディレクトリ構成

```text
ge-ai-handson/
├── README.md
├── AGENTS.md                        # Antigravity 自動読み込みルール
├── tutorial.md
├── data/
│   ├── users.csv                    # ユーザーマスタ 25件
│   ├── ai_audit_logs.csv            # 生成AI利用ログ 100件
│   ├── users_schema.json
│   └── ai_audit_schema.json
├── theme1_usage_dashboard/          # サブテーマ1: 利用量可視化 Web ダッシュボード
├── theme2_credit_card_audit/        # サブテーマ2: クレジットカード番号の検出 (CLI・関数)
└── samples/
    ├── sample1_usage_dashboard/     # サブテーマ1 の実装例 (Web ダッシュボード)
    ├── sample2_credit_card_audit/   # サブテーマ2 の実装例 (カード番号検出 CLI・関数)
    └── sample3_cloud_run_a2a/       # Cloud Run デプロイ・A2A 登録スクリプト・Skills 例
```

## Antigravity の起動

本ハンズオンでは Gemini Enterprise に含まれるクォータを利用し、モデルは Gemini のみを使用します。

1. Cloud Shell でリポジトリ直下 `ge-ai-handson` に移動し、`agy` を実行します。`data/` 配下を参照するため、サブディレクトリではなくリポジトリ直下 (`ge-ai-handson/`) で起動してください。
2. `Select login method:` で **2. Use a Google Cloud project** を選択します。続けて認証画面が表示された場合は **1. Continue with Google Cloud** を選び、表示された URL をブラウザで開いて認証コードを貼り付けます。
3. `Select billing model:` で **1. Subscriptions** を選択します。
4. `Select available subscription:` で対象の **Gemini Enterprise** サブスクリプションを選択します (一覧に表示されない場合は `Enter a Google Cloud project` から対象プロジェクト ID と `global` を指定します)。続けてフォルダの信頼確認が表示されたら `Yes, I trust this folder` を選択して起動します。

ローカルの VS Code 拡張機能を使う場合も、リポジトリ直下の `ge-ai-handson` フォルダを開き、**Use Business Account** > **Continue with Google Cloud** から **Subscription** を選んで対象の **Gemini Enterprise** ライセンスを選択します。

補足: ハンズオン環境では事前設定済みですが、別プロジェクトで試す場合は、対象プロジェクトへの Gemini Enterprise ライセンス割り当てと利用者への `roles/discoveryengine.agentspaceUser` 付与に加え、管理者が Google Cloud コンソールの **Gemini Enterprise** > **設定** > **AI デベロッパー ツール** を有効化しておく必要があります。

## ハンズオン内容

### パート 1: BigQuery 対話型分析エージェント
`tutorial.md` に沿って `users.csv` と `ai_audit_logs.csv` を BigQuery に登録し、対話型分析エージェントを作成して Gemini Enterprise に接続します。

### パート 2: Antigravity グループワーク
各ディレクトリの `README.md` にデータ仕様と要件を記載しています。Antigravity に該当ディレクトリの `README.md` を読み込ませて実装を進めます。

| テーマ | ディレクトリ | 内容 |
| :--- | :--- | :--- |
| サブテーマ 1 | `theme1_usage_dashboard/` | `users.csv` と `ai_audit_logs.csv` を `user_id` で結合し、部署・ユーザー別の利用状況を Web ダッシュボード (ポート `8080`) で可視化する |
| サブテーマ 2 | `theme2_credit_card_audit/` | `prompt_text` に含まれる 14 桁・16 桁のクレジットカード番号をルールベースで検出し、監査レポートを標準出力に表示する |

サブテーマ 1 の Web ダッシュボードは `agy` がポート `8080` でバックグラウンド起動するため、Cloud Shell 右上の **ウェブでプレビュー** > **ポート 8080 でプレビュー** (ローカル環境では `http://localhost:8080`) から表示したまま次の作業に進めます。サブテーマ 2 はポートを使わない CLI 実行のため競合せず、共有タイムではダッシュボードと監査レポートの両方を同時に表示できます。

## サンプルコード

- サブテーマ 1 の参考実装は `samples/sample1_usage_dashboard/README.md`、サブテーマ 2 の参考実装は `samples/sample2_credit_card_audit/README.md` を参照してください。
- Agent Development Kit (ADK) 2.0 を使った Cloud Run デプロイと Gemini Enterprise への Agent2Agent (A2A) 登録スクリプト、Skills の定義例は `samples/sample3_cloud_run_a2a/README.md` にまとめています。
