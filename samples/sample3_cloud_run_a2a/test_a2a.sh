#!/usr/bin/env bash
# デプロイ済み Cloud Run A2A エージェントの Agent Card 取得と JSON-RPC 応答を検証するスクリプト
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_CARD_PATH="${SCRIPT_DIR}/agent_card.json"

AGENT_URL="${1:-}"
if [[ -z "${AGENT_URL}" && -f "${AGENT_CARD_PATH}" ]]; then
  AGENT_URL="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["url"])' "${AGENT_CARD_PATH}")"
fi

if [[ -z "${AGENT_URL}" ]]; then
  echo "使い方: bash ./samples/sample3_cloud_run_a2a/test_a2a.sh <CLOUD_RUN_URL>  (または先に bash ./samples/sample3_cloud_run_a2a/deploy_a2a.sh を実行してください)" >&2
  exit 1
fi

TOKEN="$(gcloud auth print-identity-token)"

echo "=== 1. Agent Card エンドポイントの確認 (${AGENT_URL}/.well-known/agent-card.json) ==="
if ! curl -fsS -H "Authorization: Bearer ${TOKEN}" "${AGENT_URL}/.well-known/agent-card.json" | python3 -m json.tool; then
  curl -fsS -H "Authorization: Bearer ${TOKEN}" "${AGENT_URL}/.well-known/agent.json" | python3 -m json.tool
fi

echo ""
echo "=== 2. A2A JSON-RPC (message/send) による監査クエリの疎通テスト ==="
PAYLOAD='{
  "jsonrpc": "2.0",
  "id": "handson-test-001",
  "method": "message/send",
  "params": {
    "message": {
      "messageId": "msg-handson-001",
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "監査ログ100件から14桁または16桁のクレジットカード番号が混入している件数と部署別の内訳を教えて"
        }
      ]
    }
  }
}'

curl -fsS -X POST "${AGENT_URL}/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool
