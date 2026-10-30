import copy
import datetime as dt
import unittest
from unittest.mock import patch

from marketing_diagnosis.db_loader import DEFAULT_MYSQL_TABLES
from marketing_diagnosis.latest import normalize_dataset, process
from marketing_diagnosis.report_opening import patch_opening_html
from marketing_diagnosis.report_opening_data import load_opening, order_point, order_totals
from marketing_diagnosis.reporting_current import build_html, build_markdown


NOW = dt.datetime(2026, 10, 30, 16)


class Cursor:
    def __init__(self, disabled=False, missing=False, zero=False):
        self.disabled, self.missing, self.zero = disabled, missing, zero
        self.calls = []
        self.rows = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.startswith("SHOW COLUMNS"):
            if self.missing and "jd02" in sql:
                raise RuntimeError("missing_table")
            fields = {"id", "hotel_id", "business_date", "checkin_status", "order_id",
                      "order_source", "snapshot_time", "review_time", "review_id",
                      "metric_code", "metric_value", "metric_unit", "peer_average",
                      "competitor_rank", "competition_circle_hotel_count"}
            self.rows = [{"Field": field} for field in fields]
        elif "FROM hotels" in sql:
            self.rows = [{"config_json": {"channels": ["meituan"] if self.disabled else ["meituan", "ctrip"]}}]
        elif "ROW_NUMBER()" in sql:
            self.rows = [] if self.zero else [{"order_source": "美团", "count": 2}, {"order_source": "携程", "count": 1}]
        elif "jd02" in sql:
            self.rows = [{"count": 0 if self.zero else 3}]
        elif "review_detail" in sql:
            self.rows = [{"count": 2 if "meituan" in sql else 1}]
        elif "competition_metrics_30d" in sql:
            self.rows = [{"competition_circle_hotel_count": 10}]
        elif "business_metrics" in sql:
            mt = "meituan" in sql
            self.rows = [{"metric_code": "PAY_ORDER_CNT" if mt else "booking_order_count",
                          "business_date": "2026-10-29",
                          "metric_value": 10 if mt else 5, "metric_unit": "order",
                          "peer_average": 2 if mt else 3, "competitor_rank": "1/5" if mt else "3",
                          "snapshot_time": NOW - dt.timedelta(minutes=10)}]
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return copy.deepcopy(self.rows)


def opening(cursor=None):
    with patch("marketing_diagnosis.report_opening_data.report_time", return_value=NOW):
        return load_opening(cursor or Cursor(), DEFAULT_MYSQL_TABLES, "audit", "ctrip-audit", ["meituan", "ctrip"])


class ReportOpeningTests(unittest.TestCase):
    def test_rates_and_weighted_platform_totals(self):
        result = opening()
        self.assertFalse(result["participates_in_score"])
        self.assertEqual(result["reviews"]["total"]["rate"], 1)
        total = result["orders"]["daily_totals"][0]
        self.assertEqual((total["own_orders"], total["market_orders"], total["share"]), (15, 40, .375))
        self.assertEqual(result["orders"]["platforms"][0]["daily_points"][0]["market_orders"], 10)
        self.assertEqual(result["orders"]["platforms"][1]["daily_points"][0]["merchant_count"], 10)
        self.assertEqual(result["order_period_start"], "2026-10-23")
        self.assertEqual(result["checkout_date"], "2026-10-29")
        self.assertEqual(result["review_date"], "2026-10-30")

    def test_sql_has_exact_scope_dates_status_and_order_dedup(self):
        cursor = Cursor()
        opening(cursor)
        checkout = next((s, p) for s, p in cursor.calls if "ROW_NUMBER()" in s)
        self.assertIn("PARTITION BY order_id", checkout[0])
        self.assertIn("hotel_id=%s", checkout[0])
        self.assertEqual(checkout[1][:4], ("audit", "2026-10-29", "2026-10-30", "已退房"))
        review = next((s, p) for s, p in cursor.calls if "ctrip_ota_review_detail" in s and not s.startswith("SHOW"))
        self.assertEqual(review[1][:3], ("ctrip-audit", "2026-10-30", "2026-10-31"))
        self.assertIn("COUNT(DISTINCT", review[0])
        self.assertNotIn("review_content", review[0])
        orders = next((s, p) for s, p in cursor.calls if "FROM `meituan_ota_business_metrics`" in s and not s.startswith("SHOW"))
        self.assertEqual(orders[1][:3], ("audit", "2026-10-23", "2026-10-30"))

    def test_missing_order_dates_are_not_filled_or_counted_as_zero(self):
        def point(day, own, market):
            return {"business_date": day, "platform": "meituan", "own_orders": own, "market_orders": market}
        result = order_totals([
            {"platform": "meituan", "daily_points": [point("2026-10-23", 2, 10), point("2026-10-29", 4, 20)]},
            {"platform": "ctrip", "daily_points": []},
        ])
        self.assertEqual([r["business_date"] for r in result], ["2026-10-23", "2026-10-29"])
        self.assertEqual(result[0]["share"], .2)

    def test_disabled_channel_is_never_queried_or_displayed(self):
        cursor = Cursor(disabled=True)
        result = opening(cursor)
        self.assertEqual([r["platform"] for r in result["reviews"]["platforms"]], ["meituan"])
        self.assertFalse(any("ctrip_ota_" in sql for sql, _ in cursor.calls))

    def test_missing_source_and_zero_denominator_are_not_zero_rates(self):
        for cursor in [Cursor(missing=True), Cursor(zero=True)]:
            result = opening(cursor)
            self.assertIsNone(result["reviews"]["total"]["rate"])
            self.assertEqual(result["reviews"]["total"]["review_count"], 3)
        self.assertIsNone(order_point([], "ctrip")["market_orders"])

    def test_flow_fallback_is_same_batch_and_does_not_override_pay(self):
        rows = [{"metric_code": "PAY_ORDER_CNT", "metric_value": 4,
                 "peer_average": 3, "competitor_rank": "2/10", "snapshot_time": "current"},
                {"metric_code": "FLOW_PAY_ORDER_CNT", "metric_value": 99,
                 "peer_average": 99, "snapshot_time": "old"}]
        self.assertEqual(order_point(rows, "meituan")["market_orders"], 30)
        rows[0]["metric_value"] = None
        self.assertIsNone(order_point(rows, "meituan")["own_orders"])

    def test_no_score_change_and_opening_between_overview_and_summary(self):
        original = process(normalize_dataset({}))
        data = normalize_dataset({"report_opening": opening()})
        result = process(data)
        self.assertEqual(original["visual_diagnosis"], result["visual_diagnosis"])
        self.assertEqual(original["ctrip_items"], result["ctrip_items"])
        result.update(hotel_id="audit", hotel_name="测试酒店", period_start="2026-10-01", period_end="2026-10-30")
        document = build_html(result)
        self.assertEqual(document.count("class='report-opening'"), 2)
        for prefix in ("", "ctrip-"):
            overview = document.index("id='" + prefix + "overview'")
            opening_index = document.index("class='report-opening'", overview)
            self.assertLess(overview, opening_index)
            self.assertLess(opening_index, document.index("id='" + prefix + "summary'"))
        self.assertIn("37.50%", document)
        self.assertEqual(patch_opening_html(document, result), document)
        self.assertIn("昨日点评率", build_markdown(result))


if __name__ == "__main__":
    unittest.main()
