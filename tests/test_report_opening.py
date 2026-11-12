import copy
import datetime as dt
import unittest
from unittest.mock import patch

from marketing_diagnosis.db_loader import DEFAULT_MYSQL_TABLES
from marketing_diagnosis.latest import normalize_dataset, process
from marketing_diagnosis.meituan_market_share import METRIC_CODE, SECTION
from marketing_diagnosis.report_opening import patch_opening_html, _chart
from marketing_diagnosis.report_opening_data import CTRIP_ROOM_NIGHTS, load_opening, room_night_totals
from marketing_diagnosis.reporting_current import build_html, build_markdown


NOW = dt.datetime(2026, 10, 30, 16)
MEITUAN_ROWS = [{"hotel_id": "audit", "metric_code": METRIC_CODE, "business_date": "2026-10-29",
                "metric_value": 10, "metric_unit": "间夜", "peer_average": 2,
                "competitor_rank": "1/5", "snapshot_time": NOW - dt.timedelta(minutes=10)}]


class Cursor:
    def __init__(self, disabled=False, missing=False, zero=False):
        self.disabled, self.missing, self.zero = disabled, missing, zero
        self.calls = []
        self.rows = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.startswith("SHOW COLUMNS"):
            if self.missing and "_ota_order_detail" in sql:
                raise RuntimeError("missing_table")
            fields = {"id", "hotel_id", "business_date", "checkin_status", "order_id", "main_checkin_id",
                      "order_source", "snapshot_time", "review_time", "review_id",
                      "metric_code", "metric_value", "metric_unit", "peer_average",
                      "competitor_rank", "competition_circle_hotel_count", "departure_date",
                      "order_status", "order_status_type", "source_platform"}
            self.rows = [{"Field": field} for field in fields]
        elif "FROM hotels" in sql:
            self.rows = [{"config_json": {"channels": ["meituan"] if self.disabled else ["meituan", "ctrip"]}}]
        elif "meituan_ota_order_detail" in sql:
            self.rows = [{"count": 0 if self.zero else 2}]
        elif "ctrip_ota_order_detail" in sql:
            self.rows = [{"count": 0 if self.zero else 1}]
        elif "review_detail" in sql:
            self.rows = [{"count": 2 if "meituan" in sql else 1}]
        elif "competition_metrics_30d" in sql:
            self.rows = [{"competition_circle_hotel_count": 10}]
        elif "business_metrics" in sql:
            self.rows = [{"business_date": "2026-10-29",
                          "metric_value": 6, "metric_unit": "room_night",
                          "peer_average": 3, "competitor_rank": "3",
                          "snapshot_time": NOW - dt.timedelta(minutes=10)}]
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return copy.deepcopy(self.rows)


def opening(cursor=None):
    with patch("marketing_diagnosis.report_opening_data.report_time", return_value=NOW):
        return load_opening(cursor or Cursor(), DEFAULT_MYSQL_TABLES, "audit", "ctrip-audit",
                            ["meituan", "ctrip"], meituan_rows=MEITUAN_ROWS)


class ReportOpeningTests(unittest.TestCase):
    def test_share_chart_breaks_at_missing_day_and_empty_history(self):
        import xml.etree.ElementTree as ET

        points = [{"business_date": f"2026-10-{day}", "share": share}
                  for day, share in [(23, .02), (24, None), (25, .03)]]
        chart = ET.fromstring(_chart(points, "合计", "test-fill"))
        self.assertEqual(len(chart.findall("polyline")), 2)
        self.assertEqual(len(chart.findall("circle")), 2)
        self.assertIn("暂无数据", _chart([], "合计", "test-fill"))

    def test_rates_and_weighted_platform_totals(self):
        result = opening()
        self.assertFalse(result["participates_in_score"])
        self.assertEqual(result["reviews"]["total"]["rate"], 1)
        nights = result["room_nights"]
        total = nights["daily_totals"][0]
        self.assertEqual((total["own_room_nights"], total["market_room_nights"], total["share"]), (16, 48, 16 / 48))
        self.assertEqual(nights["platforms"][0]["daily_points"][0]["market_room_nights"], 18)
        self.assertEqual(nights["platforms"][1]["daily_points"][0]["hotel_count"], 10)
        self.assertEqual(nights["period_start"], "2026-10-23")
        self.assertEqual(result["checkout_date"], "2026-10-29")
        self.assertEqual(result["review_date"], "2026-10-29")

    def test_sql_has_exact_scope_dates_status_and_order_dedup(self):
        cursor = Cursor()
        opening(cursor)
        self.assertFalse(any("jd02" in sql for sql, _ in cursor.calls))
        mt_checkout = next((s, p) for s, p in cursor.calls if s.startswith("SELECT") and "meituan_ota_order_detail" in s)
        self.assertIn("COUNT(DISTINCT NULLIF(TRIM(order_id)", mt_checkout[0])
        self.assertEqual(mt_checkout[1][:4], ("audit", "2026-10-29", "2026-10-30", "CONSUMED"))
        review = next((s, p) for s, p in cursor.calls if "ctrip_ota_review_detail" in s and not s.startswith("SHOW"))
        self.assertEqual(review[1][:3], ("ctrip-audit", "2026-10-29", "2026-10-30"))
        self.assertIn("COUNT(DISTINCT", review[0])
        self.assertNotIn("review_content", review[0])
        checkout = next((s, p) for s, p in cursor.calls if s.startswith("SELECT") and "FROM `ctrip_ota_order_detail`" in s)
        self.assertEqual(checkout[1][:5], ("ctrip-audit", "2026-10-29", "2026-10-30", "已过离店日期", "CheckIn"))
        nights = next(p for s, p in cursor.calls if s.startswith("SELECT") and "FROM `ctrip_ota_business_metrics`" in s)
        self.assertEqual(nights[:4], ("ctrip-audit", "2026-10-23", "2026-10-30", CTRIP_ROOM_NIGHTS))
        count = next(p for s, p in cursor.calls if s.startswith("SELECT") and "FROM `ctrip_ota_competition_metrics_30d`" in s)
        self.assertEqual(count[:2], ("ctrip-audit", CTRIP_ROOM_NIGHTS))

    def test_missing_room_night_dates_are_not_filled_or_counted_as_zero(self):
        def point(day, own, market):
            return {"business_date": day, "own_room_nights": own, "market_room_nights": market}
        result = room_night_totals([
            {"platform": "meituan", "daily_points": [point("2026-10-23", 2, 10), point("2026-10-29", 4, 20)]},
            {"platform": "ctrip", "daily_points": []},
        ])
        self.assertEqual([r["business_date"] for r in result], ["2026-10-23", "2026-10-29"])
        self.assertEqual(result[0]["share"], .2)

    def test_disabled_channel_is_never_queried_or_displayed(self):
        cursor = Cursor(disabled=True)
        result = opening(cursor)
        self.assertEqual([r["platform"] for r in result["reviews"]["platforms"]], ["meituan"])
        self.assertEqual(result["reviews"]["total"]["checkout_orders"], 2)
        self.assertFalse(any("ctrip_ota_" in sql for sql, _ in cursor.calls))

    def test_checkout_total_requires_all_enabled_channel_counts(self):
        for ctrip, expected in ((0, 1), (None, None)):
            with self.subTest(ctrip=ctrip), patch("marketing_diagnosis.report_opening_data._ota_checkouts",
                       side_effect=[1, ctrip]):
                total = opening()["reviews"]["total"]
            self.assertEqual(total["checkout_orders"], expected)

    def test_missing_source_and_zero_denominator_are_not_zero_rates(self):
        for cursor in [Cursor(missing=True), Cursor(zero=True)]:
            result = opening(cursor)
            self.assertIsNone(result["reviews"]["total"]["rate"])
            self.assertEqual(result["reviews"]["total"]["review_count"], 3)

    def test_meituan_opening_uses_same_daily_point_as_rule_three(self):
        data = normalize_dataset({"hotel_id": "audit", SECTION: MEITUAN_ROWS, "report_opening": opening()})
        result = process(data)
        item = next(row for row in result["visual_diagnosis"]["items"] if row.get("market_share"))
        self.assertEqual(item["market_share"]["yesterday"],
                         result["report_opening"]["room_nights"]["platforms"][0]["daily_points"][0])

    def test_no_score_change_and_opening_between_overview_and_summary(self):
        with patch("marketing_diagnosis.meituan_market_share.report_time", return_value=NOW):
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
        self.assertIn("33.33%", document)
        self.assertIn("美团入住间夜 · 携程在店间夜", document)
        self.assertIn("昨日新增评论", document)
        self.assertNotIn("今日新增评论", document)
        self.assertIn("近7天间夜与商圈占比", build_markdown(result))
        self.assertEqual(patch_opening_html(document, result), document)
        self.assertIn("昨日点评率", build_markdown(result))


if __name__ == "__main__":
    unittest.main()
