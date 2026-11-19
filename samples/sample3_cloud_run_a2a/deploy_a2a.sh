#!/usr/bin/env bash
# ルールベース ADK エージェントを Cloud Run にデプロイし、Gemini Enterprise 登録用の agent_card.json を生成するスクリプト
set -euo pipefail

if [[ -f "${HOME}/.ge_handson_env" ]]; then
  # Step 1 で保存した GOOGLE_CLOUD_PROJECT / USER_ID を自動で読み込む
  # shellcheck disable=SC1091
  . "${HOME}/.ge_handson_env"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n 1 || true)"
if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
  echo "エラー: この実行環境からは gcloud の認証情報を参照できません。" >&2
  echo "Antigravity (agy) のサンドボックス内からは Cloud Shell の認証情報にアクセスできないため、" >&2
  echo "agy で実行する場合は run_command に BypassSandbox: true を指定して再実行するか、" >&2
  echo "Cloud Shell 上部の + アイコンで新しいターミナルタブを開いて直接以下を実行してください:" >&2
  echo "  bash ./samples/sample3_cloud_run_a2a/deploy_a2a.sh" >&2
  exit 1
fi

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "エラー: Google Cloud プロジェクトIDが設定されていません。" >&2
  echo "gcloud config set project <PROJECT_ID> を実行してから再実行してください。" >&2
  exit 1
fi

REGION="${CLOUD_RUN_REGION:-us-central1}"
ACCOUNT_LOCAL="$(echo "${ACTIVE_ACCOUNT}" | cut -d'@' -f1)"
DEFAULT_USER_ID="$(echo "${ACCOUNT_LOCAL:-user01}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g; s/__*/_/g; s/^_//; s/_$//')"
DEFAULT_USER_SLUG="$(echo "${ACCOUNT_LOCAL:-user01}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/--*/-/g; s/^-//; s/-$//' | cut -c1-20 | sed 's/-$//')"

USER_ID="${USER_ID:-${DEFAULT_USER_ID:-user01}}"
USER_SLUG="${USER_SLUG:-$(echo "${USER_ID}" | tr '_' '-' | cut -c1-20 | sed 's/-$//')}"
SERVICE_NAME="${SERVICE_NAME:-ai-audit-agent-${USER_SLUG}}"
AGENT_NAME="${AGENT_NAME:-ai_audit_agent_${USER_ID}}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-ge-agent-sa}"
AGENT_SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=== 1. コンテナ同梱用に data/*.csv をステージング ==="
mkdir -p "${SCRIPT_DIR}/audit_agent/data"
cp "${REPO_ROOT}/data/users.csv" "${SCRIPT_DIR}/audit_agent/data/users.csv"
cp "${REPO_ROOT}/data/ai_audit_logs.csv" "${SCRIPT_DIR}/audit_agent/data/ai_audit_logs.csv"

DEPLOY_SA_ARGS=()
if gcloud iam service-accounts describe "${AGENT_SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "専用サービスアカウント (${AGENT_SA_EMAIL}) を使用してビルド・デプロイします。"
  DEPLOY_SA_ARGS+=(
    "--service-account=${AGENT_SA_EMAIL}"
    "--build-service-account=projects/${PROJECT_ID}/serviceAccounts/${AGENT_SA_EMAIL}"
  )
else
  echo "専用サービスアカウント (${AGENT_SA_EMAIL}) 未作成の環境のため、既定のサービスアカウントを使用します。"
fi

echo "=== 2. Cloud Run (${REGION}) へルールベース A2A サーバーをデプロイ ==="
gcloud run deploy "${SERVICE_NAME}" \
  --source "${SCRIPT_DIR}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  ${DEPLOY_SA_ARGS[@]+"${DEPLOY_SA_ARGS[@]}"} \
  --no-allow-unauthenticated \
  --set-env-vars="AGENT_NAME=${AGENT_NAME}" \
  --quiet

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || true)"
if [[ -n "${PROJECT_NUMBER}" ]]; then
  DE_SA="service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com"
  gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --member="serviceAccount:${DE_SA}" \
    --role="roles/run.invoker" \
    --quiet >/dev/null 2>&1 || true
fi

AGENT_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --format='value(status.url)')"

echo "=== 3. Gemini Enterprise 登録用 agent_card.json を生成 ==="
sed -e "s|__AGENT_NAME__|${AGENT_NAME}|g" \
    -e "s|__AGENT_URL__|${AGENT_URL}|g" \
    "${SCRIPT_DIR}/agent_card.template.json" > "${SCRIPT_DIR}/agent_card.json"

echo ""
echo "デプロイ完了: ${AGENT_URL}"
echo "出力ファイル: ${SCRIPT_DIR}/agent_card.json"
echo "------------------------------------------------------------"
cat "${SCRIPT_DIR}/agent_card.json"
echo "------------------------------------------------------------"
echo "次の手順: Gemini Enterprise コンソール > エージェント > + エージェントを追加 > A2A によるカスタム エージェント へ上記 JSON を貼り付け、ユーザー権限タブで利用者を付与してください。"
