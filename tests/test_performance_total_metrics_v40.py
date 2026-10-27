from __future__ import annotations

import unittest

from marketing_diagnosis.performance_yoy_v40 import METRIC_ORDER, patch_performance_yoy
from marketing_diagnosis.reporting_v28 import _records_table


class PerformanceTotalMetricsTests(unittest.TestCase):
    def _result(self):
        return {
            "items": [
                {
                    "standard_item_id": 1,
                    "item_name": "月度经营趋势 YOY",
                    "base_score": 10,
                    "data_status": "success",
                    "score_ratio": 1,
                    "item_score": 10,
                    "fields": [],
                }
            ]
        }

    def _row(self, day, metric, daily, monthly, yearly, category="总营业指标", snapshot="2026-07-16 08:00:00"):
        return {
            "business_date": day,
            "category": category,
            "metric_name": metric,
            "room_type_id": None,
            "value_day": daily,
            "value_month": monthly,
            "value_year": yearly,
            "snapshot_time": snapshot,
        }

    def test_uses_exact_dates_total_category_and_fixed_order(self):
        rows = []
        for index, metric in enumerate(METRIC_ORDER, start=1):
            rows.append(self._row("2026-07-16", metric, index, index * 10, index * 100))
            rows.append(self._row("2025-07-16", metric, index / 2, index * 5, index * 50, snapshot="2025-07-16 08:00:00"))

        # These rows must never appear in the customer table.
        rows.append(self._row("2026-07-16", "小计", 999, 999, 999))
        rows.append(self._row("2026-07-16", "房费", 888, 888, 888, category="门店收入"))
        rows.append(self._row("2025-07-15", "房费", 777, 777, 777))

        result = self._result()
        patch_performance_yoy(result, {"hotel_performance_daily": rows})
        item = result["items"][0]

        self.assertEqual([record["metric_name"] for record in item["records"]], list(METRIC_ORDER))
        self.assertEqual(item["fields"][0]["value"], "2026-07-16")
        self.assertEqual(item["fields"][1]["value"], "2025-07-16")
        revenue = next(record for record in item["records"] if record["metric_name"] == "房费")
        self.assertEqual(revenue["value_day"], 7)
        self.assertEqual(revenue["previous_value_day"], 3.5)
        self.assertAlmostEqual(revenue["yoy_day"], 1.0)
        self.assertEqual(revenue["value_month"], 70)
        self.assertEqual(revenue["previous_value_month"], 35)
        self.assertAlmostEqual(revenue["yoy_month"], 1.0)
        self.assertEqual(revenue["value_year"], 700)
        self.assertEqual(revenue["previous_value_year"], 350)
        self.assertEqual(item["item_score"], 10)

    def test_monthly_revenue_decline_uses_the_same_yoy_for_scoring(self):
        rows = [
            self._row("2026-07-16", "房费", 70, 70, 70),
            self._row("2025-07-16", "房费", 100, 100, 100),
        ]
        result = self._result()
        patch_performance_yoy(result, {"hotel_performance_daily": rows})
        item = result["items"][0]

        revenue = next(record for record in item["records"] if record["metric_name"] == "房费")
        self.assertAlmostEqual(revenue["yoy_month"], -0.3)
        self.assertEqual(item["item_score"], 0)

    def test_zero_current_revenue_scores_as_full_decline(self):
        rows = [
            self._row("2026-07-16", "房费", 0, 0, 0),
            self._row("2025-07-16", "房费", 100, 100, 100),
        ]
        result = self._result()
        patch_performance_yoy(result, {"hotel_performance_daily": rows})

        self.assertEqual(result["items"][0]["item_score"], 0)

    def _monthly_item(self, rows):
        result = self._result()
        patch_performance_yoy(result, {"hotel_monthly": rows})
        return result["items"][0]

    def test_jy03_latest_month_uses_prior_year_month_for_display_and_score(self):
        item = self._monthly_item([
            {"period_month": "2026-09", "room_revenue": 70},
            {"period_month": "2025-09", "room_revenue": 100},
            {"period_month": "2026-10", "room_revenue": 195900.81,
             "adr": 191.50, "occupancy_rate": 78.27, "revpar": 122.59},
            {"period_month": "2025-10", "room_revenue": 83115.90,
             "adr": 183.48, "occupancy_rate": 91.52, "revpar": 125.55},
        ])
        period = item["trend_periods"][-1]
        self.assertEqual(period["current_range"], "2026/10")
        self.assertEqual(period["previous_range"], "2025/10")
        for metric, previous in zip(period["metrics"], [83115.90, 183.48, 91.52, 125.55]):
            self.assertEqual(metric["previous"], previous)
            self.assertAlmostEqual(metric["yoy"], (metric["current"] - previous) / previous)
        self.assertEqual(item["fields"][1]["value"], "2026-10")
        self.assertEqual(item["records"][0]["previous_value_month"], 83115.90)
        self.assertEqual(item["item_score"], 10)
        self.assertNotIn("仅作展示", item["scoring_note"])

    def test_jy03_keeps_latest_snapshot_for_each_month(self):
        item = self._monthly_item([
            {"period_month": "2026-10", "room_revenue": 150, "snapshot_time": "2026-10-27 10:00:00"},
            {"period_month": "2026-10", "room_revenue": 50, "snapshot_time": "2026-10-26 10:00:00"},
            {"period_month": "2025-10", "room_revenue": 100},
        ])
        self.assertEqual(item["records"][0]["value_month"], 150)
        self.assertEqual(item["item_score"], 10)

    def test_jy03_missing_prior_month_keeps_previous_scoring_month(self):
        item = self._monthly_item([
            {"period_month": "2026-10", "room_revenue": 150},
            {"period_month": "2026-09", "room_revenue": 70},
            {"period_month": "2025-09", "room_revenue": 100},
        ])
        self.assertIsNone(item["trend_periods"][-1]["metrics"][0]["previous"])
        self.assertEqual(item["fields"][1]["value"], "2026-09")
        self.assertEqual(item["item_score"], 0)

    def test_jy03_missing_or_zero_prior_revenue_does_not_invent_yoy(self):
        for prior in (None, 0):
            with self.subTest(prior=prior):
                item = self._monthly_item([
                    {"period_month": "2026-10", "room_revenue": 150},
                    {"period_month": "2025-10", "room_revenue": prior},
                ])
                self.assertIsNone(item["trend_periods"][-1]["metrics"][0]["yoy"])
                self.assertIsNone(item["item_score"])

    def test_jy03_zero_current_revenue_remains_full_decline(self):
        item = self._monthly_item([
            {"period_month": "2026-10", "room_revenue": 0},
            {"period_month": "2025-10", "room_revenue": 100},
        ])
        self.assertEqual(item["records"][0]["yoy_month"], -1)
        self.assertEqual(item["item_score"], 0)

    def test_jl02_still_takes_priority_over_jy03(self):
        result = self._result()
        patch_performance_yoy(result, {
            "hotel_performance_daily": [
                self._row("2026-10-27", "房费", 70, 70, 70),
                self._row("2025-10-27", "房费", 100, 100, 100),
            ],
            "hotel_monthly": [{"period_month": "2026-10", "room_revenue": 150},
                              {"period_month": "2025-10", "room_revenue": 100}],
        })
        self.assertEqual(result["items"][0]["item_score"], 0)
        self.assertEqual(result["items"][0]["records"][6]["value_month"], 70)

    def test_current_pipeline_applies_jy03_comparison_to_both_channels(self):
        from marketing_diagnosis.latest import build_html, process

        result = process({"hotel_id": "test", "platform": "multi", "sections": {
            "hotel_monthly": [
                {"period_month": "2026-10", "room_revenue": 195900.81},
                {"period_month": "2025-10", "room_revenue": 83115.90},
            ],
        }})
        visual = result["visual_diagnosis"]
        meituan = next(item for item in visual["items"] if item["standard_item_id"] == 1)
        ctrip = result["ctrip_items"]["1"]
        for item in (meituan, ctrip):
            self.assertEqual(item["item_score"], 10)
            self.assertEqual(item["records"][0]["previous_value_month"], 83115.90)
        html = build_html(result)
        self.assertIn("83,115.90", html)
        self.assertNotIn("本月，无YOY", html)
        self.assertNotIn("本月数据仅作展示", html)

    def test_report_uses_daily_monthly_yearly_wording(self):
        item = self._result()["items"][0]
        item["records"] = [
            {
                "metric_name": "房费",
                "value_day": 4000,
                "previous_value_day": 3500,
                "yoy_day": 0.142857,
                "value_month": 62616.49,
                "previous_value_month": 60000,
                "yoy_month": 0.043608,
                "value_year": 780581.21,
                "previous_value_year": 700000,
                "yoy_year": 0.115116,
            }
        ]
        html = _records_table(item)
        for header in (
            "日度",
            "同期日度",
            "日度YOY",
            "月度",
            "同期月度",
            "月度YOY",
            "年度",
            "同期年度",
            "年度YOY",
        ):
            self.assertIn(f"<th>{header}</th>", html)
        self.assertNotIn("去年本月", html)
        self.assertNotIn("本年YOY", html)


if __name__ == "__main__":
    unittest.main()
