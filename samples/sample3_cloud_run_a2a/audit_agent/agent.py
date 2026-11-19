"""ADK 2.0 ルールベース監査エージェント: 部署別 AI 利用量集計とクレジットカード番号 (14桁・16桁) 検出."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import csv
import os
from pathlib import Path
import re
from typing import Any

from google.adk.agents import BaseAgent, InvocationContext
from google.adk.events import Event
from google.genai import types


AGENT_NAME = os.environ.get("AGENT_NAME", "ai_governance_auditor")


def _resolve_data_dir() -> Path:
    """コンテナ内 (./data/) とローカルリポジトリ階層の両方から安全に data ディレクトリを解決する."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "data", *(parent / "data" for parent in here.parents)):
        if (candidate / "users.csv").exists():
            return candidate
    return here / "data"


DATA_DIR = _resolve_data_dir()

CARD_PATTERN = re.compile(
    r"(?<![0-9A-Za-z_-])(?:"
    r"(?P<sep16>[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{4}|[0-9]{4} [0-9]{4} [0-9]{4} [0-9]{4})"
    r"|(?P<raw16>[0-9]{16})"
    r"|(?P<sep14>[0-9]{4}-[0-9]{6}-[0-9]{4}|[0-9]{4} [0-9]{6} [0-9]{4})"
    r"|(?P<raw14>[0-9]{14})"
    r")(?![0-9A-Za-z_-])"
)

RULE_LABELS: dict[str, tuple[str, int]] = {
    "sep16": ("16桁 (4-4-4-4 区切り)", 16),
    "raw16": ("16桁 (連続数字)", 16),
    "sep14": ("14桁 (4-6-4 区切り)", 14),
    "raw14": ("14桁 (連続数字)", 14),
}

KNOWN_DEPARTMENTS = (
    "開発本部",
    "AI統括部",
    "データ統括部",
    "情報システム部",
    "営業本部",
    "人事総務部",
)

CARD_KEYWORDS = ("カード", "クレジット", "14桁", "16桁", "混入", "luhn", "pan", "漏洩")
USAGE_KEYWORDS = (
    "利用量",
    "利用状況",
    "利用率",
    "トークン",
    "リクエスト",
    "ランキング",
    "未利用",
    "アクティブ",
    "モデル別",
    "モデルごと",
    "使って",
)


def _check_luhn(digits_only: str) -> bool:
    """数字列が Luhn チェックディジットを満たすか判定する."""
    if not (digits_only.isascii() and digits_only.isdigit()) or len(digits_only) not in (14, 16):
        return False
    total = 0
    for idx, ch in enumerate(reversed(digits_only)):
        d = ord(ch) - 48
        if idx % 2 == 1:
            doubled = d * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += d
    return total % 10 == 0


def _detect_card_brand(digits_only: str) -> str:
    """数字列の先頭プレフィックス (IIN/BIN) と桁数から国際ブランド名を返す."""
    if not (digits_only.isascii() and digits_only.isdigit()) or len(digits_only) not in (14, 16):
        return "Other"
    p2, p3, p4 = int(digits_only[:2]), int(digits_only[:3]), int(digits_only[:4])
    if len(digits_only) == 16:
        if digits_only.startswith("4"):
            return "Visa"
        if 51 <= p2 <= 55 or 2221 <= p4 <= 2720:
            return "Mastercard"
        if 3528 <= p4 <= 3589:
            return "JCB"
    elif 300 <= p3 <= 305 or p2 in (36, 38, 39):
        return "Diners Club"
    return "Other"


def _mask_card_number(raw_val: str) -> str:
    """区切り文字を維持したまま末尾4桁以外の数字を * に置換する."""
    to_mask = max(0, sum(ch.isdigit() for ch in raw_val) - 4)
    out: list[str] = []
    masked = 0
    for ch in raw_val:
        if ch.isdigit() and masked < to_mask:
            out.append("*")
            masked += 1
        else:
            out.append(ch)
    return "".join(out)


def _scan_cards_in_text(text: str, require_luhn: bool = True) -> tuple[list[dict[str, Any]], str]:
    """文字列から 14桁・16桁カード番号を出現順に抽出し、(検出一覧, マスク済み文字列) を返す."""
    findings: list[dict[str, Any]] = []
    parts: list[str] = []
    cursor = 0
    for match in CARD_PATTERN.finditer(text):
        group_key = match.lastgroup
        if group_key is None:
            continue
        rule_name, digit_len = RULE_LABELS[group_key]
        raw_val = match.group(0)
        digits = raw_val.replace("-", "").replace(" ", "")
        luhn_ok = _check_luhn(digits)
        if require_luhn and not luhn_ok:
            continue
        masked_val = _mask_card_number(raw_val)
        start, end = match.span()
        parts.append(text[cursor:start])
        parts.append(masked_val)
        cursor = end
        findings.append(
            {
                "card_brand": _detect_card_brand(digits),
                "rule_name": rule_name,
                "digit_length": digit_len,
                "masked_number": masked_val,
                "luhn_valid": luhn_ok,
            }
        )
    parts.append(text[cursor:])
    return findings, "".join(parts)


def summarize_department_usage(department_filter: str = "") -> dict[str, Any]:
    """users.csv と ai_audit_logs.csv を user_id で結合し、部署別・ユーザー別の生成AI利用量を集計する."""
    users_path = DATA_DIR / "users.csv"
    logs_path = DATA_DIR / "ai_audit_logs.csv"

    users_by_id: dict[str, dict[str, Any]] = {}
    dept_stats: dict[str, dict[str, Any]] = {}

    with users_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            uid = row["user_id"].strip()
            dept = row["department"].strip()
            users_by_id[uid] = {
                "user_id": uid,
                "user_name": row["user_name"].strip(),
                "department": dept,
                "job_role": row["job_role"].strip(),
                "requests": 0,
                "total_tokens": 0,
            }
            d = dept_stats.setdefault(
                dept,
                {
                    "department": dept,
                    "licensed_users": 0,
                    "active_user_ids": set(),
                    "requests": 0,
                    "total_tokens": 0,
                },
            )
            d["licensed_users"] += 1

    with logs_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            uid = row["user_id"].strip()
            tokens = int(row["input_tokens"]) + int(row["output_tokens"])
            user = users_by_id.get(uid)
            if user is None:
                user = {
                    "user_id": uid,
                    "user_name": uid,
                    "department": "未登録部署",
                    "job_role": "-",
                    "requests": 0,
                    "total_tokens": 0,
                }
                users_by_id[uid] = user
                d_unregistered = dept_stats.setdefault(
                    "未登録部署",
                    {
                        "department": "未登録部署",
                        "licensed_users": 0,
                        "active_user_ids": set(),
                        "requests": 0,
                        "total_tokens": 0,
                    },
                )
                d_unregistered["licensed_users"] += 1
            user["requests"] += 1
            user["total_tokens"] += tokens
            d = dept_stats[user["department"]]
            d["active_user_ids"].add(uid)
            d["requests"] += 1
            d["total_tokens"] += tokens

    departments = sorted(
        (
            {
                "department": d["department"],
                "licensed_users": d["licensed_users"],
                "active_users": len(d["active_user_ids"]),
                "inactive_users": d["licensed_users"] - len(d["active_user_ids"]),
                "requests": d["requests"],
                "total_tokens": d["total_tokens"],
            }
            for d in dept_stats.values()
            if not department_filter or department_filter in d["department"]
        ),
        key=lambda x: (x["total_tokens"], x["requests"]),
        reverse=True,
    )

    filtered_users = [
        u
        for u in users_by_id.values()
        if not department_filter or department_filter in u["department"]
    ]
    top_users = sorted(
        filtered_users,
        key=lambda x: (-x["total_tokens"], -x["requests"], x["user_id"]),
    )[:5]
    inactive_users = sorted(
        (
            {"user_id": u["user_id"], "user_name": u["user_name"], "department": u["department"]}
            for u in filtered_users
            if u["requests"] == 0
        ),
        key=lambda x: x["user_id"],
    )

    return {
        "department_filter": department_filter or "全部署",
        "departments": departments,
        "top_users": top_users,
        "inactive_users": inactive_users,
    }


def audit_credit_card_numbers(target_text: str = "", require_luhn: bool = True) -> dict[str, Any]:
    """テキストまたは監査ログ全体をルールベースで走査し、14桁・16桁のクレジットカード番号混入を返す."""
    if target_text.strip():
        hits, masked_text = _scan_cards_in_text(target_text, require_luhn=require_luhn)
        return {
            "mode": "single_text",
            "violation_count": len(hits),
            "masked_text": masked_text,
            "findings": hits,
        }

    users_path = DATA_DIR / "users.csv"
    logs_path = DATA_DIR / "ai_audit_logs.csv"
    with users_path.open(encoding="utf-8-sig", newline="") as f:
        users_by_id = {row["user_id"].strip(): row for row in csv.DictReader(f)}

    violations: list[dict[str, Any]] = []
    dept_counts: dict[str, int] = {}
    count_16 = 0
    count_14 = 0
    total_logs = 0

    with logs_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            total_logs += 1
            hits, masked_prompt = _scan_cards_in_text(row["prompt_text"], require_luhn=require_luhn)
            if not hits:
                continue
            uid = row["user_id"].strip()
            user = users_by_id.get(uid, {"user_name": uid, "department": "未登録部署"})
            dept = user["department"].strip()
            dept_counts[dept] = dept_counts.get(dept, 0) + len(hits)
            for h in hits:
                if h["digit_length"] == 16:
                    count_16 += 1
                else:
                    count_14 += 1
                violations.append(
                    {
                        "log_id": row["log_id"].strip(),
                        "event_timestamp": row["event_timestamp"].strip(),
                        "user_id": uid,
                        "user_name": user["user_name"].strip(),
                        "department": dept,
                        "tool_surface": row["tool_surface"].strip(),
                        "card_brand": h["card_brand"],
                        "digit_length": h["digit_length"],
                        "rule_name": h["rule_name"],
                        "masked_number": h["masked_number"],
                        "luhn_valid": h["luhn_valid"],
                        "masked_prompt": masked_prompt.strip(),
                    }
                )

    departments = [
        {"department": k, "violation_count": v}
        for k, v in sorted(dept_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "mode": "audit_log_scan",
        "total_logs_scanned": total_logs,
        "violation_count": len(violations),
        "count_16_digit": count_16,
        "count_14_digit": count_14,
        "departments": departments,
        "violations": violations,
    }


def _escape_md(text: str) -> str:
    """Markdown パーサーで * や _ が装飾記号として消えるのを防ぐ."""
    return (
        text.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
    )


def _format_usage_section(data: dict[str, Any]) -> str:
    depts = data["departments"]
    total_req = sum(d["requests"] for d in depts)
    total_tok = sum(d["total_tokens"] for d in depts)
    total_lic = sum(d["licensed_users"] for d in depts)
    total_act = sum(d["active_users"] for d in depts)
    total_inact = total_lic - total_act

    lines = [
        f"## 生成AI利用量集計 ({data['department_filter']})",
        "",
        (
            f"対象範囲の合計は **{total_req:,} 件** / **{total_tok:,} tokens**、"
            f"アクティブ人数は **{total_act} / {total_lic} 名** (未利用 **{total_inact} 名**) です。"
        ),
        "",
        "### 部署別ランキング",
        "",
        "| 順位 | 部署 | リクエスト数 | 合計トークン | 1人あたりトークン | 稼働 / 登録 |",
        "| :---: | :--- | ---: | ---: | ---: | :---: |",
    ]
    for idx, d in enumerate(depts, start=1):
        per_user = round(d["total_tokens"] / d["licensed_users"]) if d["licensed_users"] else 0
        lines.append(
            f"| {idx} | **{d['department']}** | {d['requests']:,} 件 | {d['total_tokens']:,} | "
            f"{per_user:,} | {d['active_users']} / {d['licensed_users']} 名 |"
        )

    lines.extend(
        [
            "",
            "### 利用量上位ユーザー (Top 5)",
            "",
            "| 順位 | ユーザーID | 氏名 | 部署 | リクエスト数 | 合計トークン |",
            "| :---: | :--- | :--- | :--- | ---: | ---: |",
        ]
    )
    for idx, u in enumerate(data["top_users"], start=1):
        lines.append(
            f"| {idx} | `{u['user_id']}` | {u['user_name']} | {u['department']} | "
            f"{u['requests']:,} 件 | {u['total_tokens']:,} |"
        )

    lines.extend(["", f"### 未利用ユーザー ({len(data['inactive_users'])} 名)", ""])
    if data["inactive_users"]:
        for u in data["inactive_users"]:
            lines.append(f"- `{u['user_id']}` {u['user_name']} ({u['department']})")
    else:
        lines.append("- 該当なし")
    return "\n".join(lines)


def _format_card_audit_section(data: dict[str, Any]) -> str:
    if data["mode"] == "single_text":
        lines = [
            "## 入力テキストのクレジットカード番号判定",
            "",
            f"入力テキストからクレジットカード番号パターンが **{data['violation_count']} 件** 検出されました。",
            "",
            "| ブランド | 検出パターン | マスク済み番号 | Luhn検証 |",
            "| :--- | :--- | :--- | :---: |",
        ]
        for h in data["findings"]:
            luhn_str = "有効" if h["luhn_valid"] else "無効"
            lines.append(
                f"| **{h['card_brand']}** | {h['rule_name']} | `{h['masked_number']}` | {luhn_str} |"
            )
        lines.extend(["", "### マスク済みテキスト", "", f"- {_escape_md(data['masked_text'])}"])
        return "\n".join(lines)

    dept_summary = (
        "、".join(f"**{d['department']} {d['violation_count']} 件**" for d in data["departments"])
        or "なし"
    )
    lines = [
        "## クレジットカード番号混入監査結果",
        "",
        (
            f"監査ログ **{data['total_logs_scanned']} 件** を走査し、クレジットカード番号の混入を "
            f"**{data['violation_count']} 件** (16桁: **{data['count_16_digit']} 件** / "
            f"14桁: **{data['count_14_digit']} 件**) 検出しました。発生部署の内訳は {dept_summary} です。"
        ),
        "",
        "| ログID | 発生日時 (UTC) | 部署 | 氏名 | 利用機能 | ブランド | マスク済み番号 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for v in data["violations"]:
        ts_short = v["event_timestamp"][:16].replace("T", " ")
        lines.append(
            f"| `{v['log_id']}` | {ts_short} | {v['department']} | {v['user_name']} | "
            f"{v['tool_surface']} | **{v['card_brand']}** | `{v['masked_number']}` |"
        )

    lines.extend(["", "### 該当プロンプト内容 (マスク済み)", ""])
    for v in data["violations"]:
        lines.append(
            f"- **`{v['log_id']}`** ({v['department']} / {v['user_name']} / {v['rule_name']})  \n"
            f"  {_escape_md(v['masked_prompt'])}"
        )
    return "\n".join(lines)


def build_rule_based_response(user_text: str) -> str:
    """LLM を呼び出さず、受信テキストからルールベースで集計・カード番号検出結果を生成する."""
    text = user_text.strip()
    inline_hits, _ = _scan_cards_in_text(text, require_luhn=True)
    if inline_hits:
        return _format_card_audit_section(audit_credit_card_numbers(target_text=text, require_luhn=True))

    lowered = text.lower()
    wants_card = any(k in lowered for k in CARD_KEYWORDS)
    wants_usage = any(k in lowered for k in USAGE_KEYWORDS)

    matched_depts = [d for d in KNOWN_DEPARTMENTS if d in text]
    dept_filter = matched_depts[0] if len(matched_depts) == 1 and "部署別" not in text and "全部署" not in text else ""

    sections: list[str] = []
    if wants_usage or not wants_card:
        sections.append(_format_usage_section(summarize_department_usage(department_filter=dept_filter)))
    if wants_card or not wants_usage:
        sections.append(_format_card_audit_section(audit_credit_card_numbers(require_luhn=True)))
    return "\n\n".join(sections)


def _extract_user_text(ctx: InvocationContext) -> str:
    if ctx.user_content and ctx.user_content.parts:
        texts = [p.text for p in ctx.user_content.parts if getattr(p, "text", None)]
        if texts:
            return "\n".join(texts)
    if ctx.session and getattr(ctx.session, "events", None):
        for ev in reversed(ctx.session.events):
            if getattr(ev, "author", "") == "user" and getattr(ev, "content", None) and ev.content.parts:
                texts = [p.text for p in ev.content.parts if getattr(p, "text", None)]
                if texts:
                    return "\n".join(texts)
    return ""


class RuleBasedAuditAgent(BaseAgent):
    """Gemini API を一切呼び出さずルールベースで応答する ADK カスタムエージェント."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        user_text = _extract_user_text(ctx)
        reply_text = build_rule_based_response(user_text)
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=reply_text)],
            ),
        )


root_agent = RuleBasedAuditAgent(
    name=AGENT_NAME,
    description=(
        "生成AIの利用状況集計とクレジットカード番号の混入チェックの2機能を提供するエージェントです。"
        "(1) 部署・ユーザー別のリクエスト件数・トークン数・未利用ユーザーの集計、"
        "(2) ログや入力テキスト内の14桁・16桁クレジットカード番号の検出とマスク表示に対応します。"
    ),
)
