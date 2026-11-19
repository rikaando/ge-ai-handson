"""サンプル 1 (生成AI利用量可視化ダッシュボード) の自動検証テスト."""

import unittest

import app as usage_dashboard


class TestUsageDashboard(unittest.TestCase):
    """サブテーマ 1: 部署・モデル・日別・ユーザー別利用量集計の検証."""

    def test_load_and_aggregate_counts(self) -> None:
        result = usage_dashboard.load_and_aggregate()
        summary = result["summary"]

        self.assertEqual(summary["total_requests"], 100)
        self.assertEqual(summary["licensed_users"], 25)
        self.assertEqual(summary["active_users"], 22)
        self.assertEqual(summary["inactive_users"], 3)
        self.assertGreater(summary["total_tokens"], 0)
        self.assertGreater(summary["avg_latency_ms"], 0)

        departments = {d["department"]: d for d in result["departments"]}
        self.assertEqual(len(departments), 6)
        expected_order = [
            "開発本部",
            "AI統括部",
            "データ統括部",
            "情報システム部",
            "営業本部",
            "人事総務部",
        ]
        self.assertEqual([d["department"] for d in result["departments"]], expected_order)
        self.assertEqual(
            [d["department"] for d in sorted(result["departments"], key=lambda x: x["requests"], reverse=True)],
            expected_order,
        )
        self.assertEqual(sum(d["requests"] for d in departments.values()), 100)
        self.assertEqual(sum(d["licensed_users"] for d in departments.values()), 25)
        self.assertEqual(sum(d["inactive_users"] for d in departments.values()), 3)

        self.assertEqual(len(result["models"]), 4)
        self.assertEqual(sum(m["requests"] for m in result["models"]), 100)

        daily = result["daily_trends"]
        self.assertGreater(len(daily), 0)
        self.assertEqual(sum(d["requests"] for d in daily), 100)
        self.assertEqual(sum(d["total_tokens"] for d in daily), summary["total_tokens"])

        dev_dept = departments["開発本部"]
        self.assertEqual(dev_dept["tokens_per_user"], round(dev_dept["total_tokens"] / dev_dept["licensed_users"]))
        self.assertEqual(sum(v["requests"] for v in dev_dept["model_breakdown"].values()), dev_dept["requests"])
        self.assertEqual(sum(v["requests"] for v in dev_dept["surface_breakdown"].values()), dev_dept["requests"])

        inactive_ids = sorted(u["user_id"] for u in result["users"] if u["requests"] == 0)
        self.assertEqual(inactive_ids, ["USR-0112", "USR-0121", "USR-0123"])

    def test_load_and_aggregate_filters(self) -> None:
        filtered = usage_dashboard.load_and_aggregate(department_filter="開発本部", model_filter="claude-opus-5-5")
        self.assertEqual(filtered["filters"]["selected_department"], "開発本部")
        self.assertEqual(filtered["filters"]["selected_model"], "claude-opus-5-5")
        self.assertEqual(len(filtered["departments"]), 1)
        self.assertEqual(filtered["departments"][0]["department"], "開発本部")
        self.assertEqual(len(filtered["models"]), 1)
        self.assertEqual(filtered["models"][0]["model_name"], "claude-opus-5-5")
        self.assertGreater(filtered["summary"]["total_requests"], 0)
        self.assertEqual(
            filtered["summary"]["total_requests"],
            filtered["departments"][0]["requests"],
        )


if __name__ == "__main__":
    unittest.main()
