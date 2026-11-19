"""サンプル 2 (クレジットカード番号ルールベース検出) の自動検証テスト."""

import contextlib
import io
import json
from pathlib import Path
import unittest

import credit_card_audit


RAW_TEST_CARDS = (
    "3600-000000-0008",
    "3530111333300000",
    "4111-1111-1111-1111",
    "5500 0000 0000 0004",
)


class TestCreditCardAudit(unittest.TestCase):
    """サブテーマ 2: 14桁・16桁クレジットカード番号検出とマスク出力の検証."""

    def test_detect_16_digit_formats_masked(self) -> None:
        samples = [
            ("カード番号 4111-1111-1111-1111 の決済確認", "****-****-****-1111"),
            ("番号 5500 0000 0000 0004 を入力", "**** **** **** 0004"),
            ("テスト番号3530111333300000について", "************0000"),
        ]
        for text, expected_masked in samples:
            with self.subTest(text=text):
                hits = credit_card_audit.detect_credit_cards(text)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["digit_length"], 16)
                self.assertEqual(hits[0]["masked_number"], expected_masked)
                self.assertNotIn("matched_number", hits[0])
                self.assertTrue(hits[0]["luhn_valid"])

    def test_detect_14_digit_formats_masked(self) -> None:
        samples = [
            ("法人カード 3600-000000-0008 の明細", "****-******-0008"),
            ("ダイナース 3000 000000 0004 の確認", "**** ****** 0004"),
            ("番号 38520000023237 の精算", "**********3237"),
        ]
        for text, expected_masked in samples:
            with self.subTest(text=text):
                hits = credit_card_audit.detect_credit_cards(text)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["digit_length"], 14)
                self.assertEqual(hits[0]["masked_number"], expected_masked)
                self.assertNotIn("matched_number", hits[0])
                self.assertTrue(hits[0]["luhn_valid"])

    def test_preserves_appearance_order(self) -> None:
        text = "1件目 3600-000000-0008 と 2件目 4111-1111-1111-1111 を続けて記載"
        hits = credit_card_audit.detect_credit_cards(text)
        self.assertEqual([h["masked_number"] for h in hits], ["****-******-0008", "****-****-****-1111"])

    def test_false_positive_exclusions(self) -> None:
        normal_texts = [
            "注文番号 ORD-2026101501 の配送状況を要約してください。",
            "伝票番号 202610180045 の仕訳データを確認したいです。",
            "取引先の法人番号 1010401089234 (13桁) を記載してください。",
            "バッチジョブID 202610201530991 (15桁) の遅延原因を整理して。",
            "配送追跡番号 990011223344556677 (18桁) のステータス案内文を作成して。",
            "代表窓口 03-5555-0199 および文書番号 2026-10-22-0930 を案内文に入れて。",
            "trace_id 4bf92f3577b34da6a3ce929d0e0e4736 のログを確認して。",
            "スネークケース識別子 JOB_4111111111111111 の実行履歴",
            "全角数字 ４１１１１１１１１１１１１１１１ のサンプル",
        ]
        for text in normal_texts:
            with self.subTest(text=text):
                self.assertEqual(credit_card_audit.detect_credit_cards(text, require_luhn=False), [])

    def test_scan_full_csv_dataset_without_raw_pan_leak(self) -> None:
        self.assertTrue(Path(credit_card_audit.USERS_CSV).exists())
        self.assertTrue(Path(credit_card_audit.LOGS_CSV).exists())

        for require_luhn in (False, True):
            with self.subTest(require_luhn=require_luhn):
                report = credit_card_audit.scan_audit_logs(require_luhn=require_luhn)
                summary = report["summary"]
                self.assertEqual(summary["total_logs_scanned"], 100)
                self.assertEqual(summary["violation_count"], 4)
                self.assertEqual(summary["count_16_digit"], 3)
                self.assertEqual(summary["count_14_digit"], 1)

                self.assertEqual(
                    report["departments"],
                    [
                        {"department": "営業本部", "violation_count": 3},
                        {"department": "開発本部", "violation_count": 1},
                    ],
                )

                detected_ids = [v["log_id"] for v in report["violations"]]
                self.assertEqual(
                    detected_ids,
                    [
                        "LOG-202610-037",
                        "LOG-202610-049",
                        "LOG-202610-084",
                        "LOG-202610-097",
                    ],
                )
                serialized = json.dumps(report, ensure_ascii=False)
                for raw_pan in RAW_TEST_CARDS:
                    self.assertNotIn(raw_pan, serialized)
                for item in report["violations"]:
                    self.assertIn("*", item["masked_number"])
                    self.assertIn(item["masked_number"], item["masked_prompt"])

    def test_cli_stdout_and_json_modes(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = credit_card_audit.main([])
        self.assertEqual(rc, 0)
        out_text = buf.getvalue()
        self.assertIn("検出件数     : 4 件", out_text)
        self.assertIn("****-******-0008", out_text)
        self.assertIn("************0000", out_text)
        self.assertIn("****-****-****-1111", out_text)
        self.assertIn("**** **** **** 0004", out_text)
        for raw_pan in RAW_TEST_CARDS:
            self.assertNotIn(raw_pan, out_text)

        buf_json = io.StringIO()
        with contextlib.redirect_stdout(buf_json):
            rc_json = credit_card_audit.main(["--json"])
        self.assertEqual(rc_json, 0)
        raw_json_str = buf_json.getvalue()
        for raw_pan in RAW_TEST_CARDS:
            self.assertNotIn(raw_pan, raw_json_str)
        parsed = json.loads(raw_json_str)
        self.assertEqual(parsed["summary"]["violation_count"], 4)

        buf_single = io.StringIO()
        with contextlib.redirect_stdout(buf_single):
            rc_single = credit_card_audit.main(["--text", "カード 4111-1111-1111-1111 と ORD-2026101501", "--json"])
        self.assertEqual(rc_single, 0)
        single_json_str = buf_single.getvalue()
        self.assertNotIn("4111-1111-1111-1111", single_json_str)
        parsed_single = json.loads(single_json_str)
        self.assertEqual(parsed_single["violation_count"], 1)
        self.assertEqual(parsed_single["findings"][0]["masked_number"], "****-****-****-1111")
        self.assertIn("****-****-****-1111", parsed_single["masked_text"])


if __name__ == "__main__":
    unittest.main()
