"""Cloud Run 上でルールベース ADK 監査エージェントを A2A プロトコルとして公開するエントリポイント."""

import json
import os
from pathlib import Path

from a2a.types import AgentCard
from audit_agent.agent import AGENT_NAME, root_agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
import uvicorn


os.environ.setdefault("ADK_SUPPRESS_A2A_EXPERIMENTAL_FEATURE_WARNINGS", "TRUE")

PORT = int(os.environ.get("PORT", "8080"))
AGENT_URL = os.environ.get("AGENT_URL", f"http://localhost:{PORT}")


def _load_agent_card() -> AgentCard:
    template_path = Path(__file__).resolve().parent / "agent_card.template.json"
    raw = template_path.read_text(encoding="utf-8")
    rendered = raw.replace("__AGENT_NAME__", AGENT_NAME).replace("__AGENT_URL__", AGENT_URL)
    return AgentCard.model_validate(json.loads(rendered))


app = to_a2a(root_agent, port=PORT, agent_card=_load_agent_card())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
