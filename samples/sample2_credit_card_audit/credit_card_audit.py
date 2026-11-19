"""サブテーマ 2 参考実装: クレジットカード番号 (14桁・16桁) ルールベース検出 CLI・モジュール."""

import argparse
import csv
import json
from pathlib import Path
import re
import sys
import unicodedata


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent.parent / "data"
USERS_CSV = DATA_DIR / "users.csv"
LOGS_CSV = DATA_DIR / "ai_audit_logs.csv"

# 前後に英数字・アンダースコア・ハイフンが続かない境界条件を設け、業務IDや電話番号・文書番号の誤検知を防ぐ
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


def check_luhn(digits_only: str) -> bool:
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


def detect_card_brand(digits_only: str) -> str:
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


def mask_card_number(raw_val: str) -> str:
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


def _scan_text(text: str, require_luhn: bool = True) -> tuple[list[dict], str]:
    """テキストから対象カード番号を抽出し、(検出一覧, マスク済みテキスト) を返す."""
    findings: list[dict] = []
    parts: list[str] = []
    cursor = 0
    for match in CARD_PATTERN.finditer(text):
        group_key = match.lastgroup
        if group_key is None:
            continue
        rule_name, digit_len = RULE_LABELS[group_key]
        raw_val = match.group(0)
        digits_only = raw_val.replace("-", "").replace(" ", "")
        luhn_ok = check_luhn(digits_only)
        if require_luhn and not luhn_ok:
            continue
        masked_val = mask_card_number(raw_val)
        start, end = match.span()
        parts.append(text[cursor:start])
        parts.append(masked_val)
        cursor = end
        findings.append(
            {
                "card_brand": detect_card_brand(digits_only),
                "rule_name": rule_name,
                "digit_length": digit_len,
                "masked_number": masked_val,
                "luhn_valid": luhn_ok,
            }
        )
    parts.append(text[cursor:])
    return findings, "".join(parts)


def detect_credit_cards(text: str, require_luhn: bool = True) -> list[dict]:
    """テキストから 14桁・16桁のクレジットカード番号パターンを出現順に抽出する."""
    findings, _ = _scan_text(text, require_luhn=require_luhn)
    return findings


def scan_audit_logs(
    users_path: Path = USERS_CSV,
    logs_path: Path = LOGS_CSV,
    require_luhn: bool = True,
) -> dict:
    """ログ CSV 全体を走査し、users.csv と結合して検出一覧と部署別件数を返す."""
    with users_path.open(encoding="utf-8", newline="") as f:
        users_by_id = {row["user_id"]: row for row in csv.DictReader(f)}

    violations: list[dict] = []
    dept_counts: dict[str, int] = {}
    count_16 = 0
    count_14 = 0
    total_logs = 0

    with logs_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            total_logs += 1
            hits, masked_prompt = _scan_text(row["prompt_text"], require_luhn=require_luhn)
            if not hits:
                continue
            user = users_by_id.get(
                row["user_id"],
                {"user_name": row["user_id"], "department": "未登録部署", "job_role": "-"},
            )
            dept = user["department"]
            dept_counts[dept] = dept_counts.get(dept, 0) + len(hits)
            for hit in hits:
                if hit["digit_length"] == 16:
                    count_16 += 1
                else:
                    count_14 += 1
                violations.append(
                    {
                        "event_timestamp": row["event_timestamp"],
                        "log_id": row["log_id"],
                        "user_id": row["user_id"],
                        "user_name": user["user_name"],
                        "department": dept,
                        "tool_surface": row["tool_surface"],
                        "card_brand": hit["card_brand"],
                        "digit_length": hit["digit_length"],
                        "rule_name": hit["rule_name"],
                        "masked_number": hit["masked_number"],
                        "luhn_valid": hit["luhn_valid"],
                        "masked_prompt": masked_prompt,
                    }
                )

    dept_summary = [
        {"department": dept, "violation_count": cnt}
        for dept, cnt in sorted(dept_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "summary": {
            "total_logs_scanned": total_logs,
            "violation_count": len(violations),
            "count_16_digit": count_16,
            "count_14_digit": count_14,
            "require_luhn": require_luhn,
        },
        "departments": dept_summary,
        "violations": violations,
    }


def _pad_disp(text: str, width: int) -> str:
    disp = sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)
    return text + " " * max(0, width - disp)


def format_report(report: dict) -> str:
    """監査結果の辞書をターミナル表示用のテキストに整形する."""
    s = report["summary"]
    mode_label = "境界正規表現 + Luhn検証" if s["require_luhn"] else "境界正規表現のみ"
    lines = [
        f"=== クレジットカード番号混入 監査レポート ({mode_label}) ===",
        f"走査ログ件数 : {s['total_logs_scanned']} 件",
        f"検出件数     : {s['violation_count']} 件 (16桁: {s['count_16_digit']} 件 / 14桁: {s['count_14_digit']} 件)",
        "",
        "[部署別 検出件数]",
    ]
    if report["departments"]:
        for d in report["departments"]:
            lines.append(f"  - {d['department']}: {d['violation_count']} 件")
    else:
        lines.append("  該当なし")

    lines.extend(["", "[検出ログ一覧]"])
    if report["violations"]:
        for v in report["violations"]:
            user_col = _pad_disp(f"{v['user_id']} ({v['user_name']})", 24)
            rule_col = _pad_disp(v["rule_name"], 22)
            lines.append(
                f"  - {v['log_id']} | {v['department']} | {user_col} "
                f"| {v['card_brand']:<11} | {rule_col} | {v['masked_number']}"
            )
    else:
        lines.append("  該当なし")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="サブテーマ2: クレジットカード番号混入検出ツール")
    parser.add_argument("--text", help="CSVではなく指定したテキスト単体を判定する")
    parser.add_argument("--json", action="store_true", help="結果をJSON形式で標準出力する")
    parser.add_argument("--no-luhn", action="store_true", help="Luhnチェックディジット検証を省略する")
    args = parser.parse_args(argv)

    require_luhn = not args.no_luhn

    if args.text is not None:
        findings, masked_text = _scan_text(args.text, require_luhn=require_luhn)
        if args.json:
            print(
                json.dumps(
                    {
                        "violation_count": len(findings),
                        "masked_text": masked_text,
                        "findings": findings,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif not findings:
            print("検出なし: 14桁・16桁のカード番号は含まれていません。")
        else:
            print(f"検出 ({len(findings)} 件):")
            for f in findings:
                print(f"  - {f['card_brand']} ({f['rule_name']}): {f['masked_number']} (Luhn={f['luhn_valid']})")
        return 0

    if not USERS_CSV.exists() or not LOGS_CSV.exists():
        print(f"CSVファイルが見つかりません: {USERS_CSV}, {LOGS_CSV}", file=sys.stderr)
        return 1

    report = scan_audit_logs(require_luhn=require_luhn)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
