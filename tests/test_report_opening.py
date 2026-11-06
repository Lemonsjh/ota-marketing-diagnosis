import copy
import datetime as dt
import sqlite3
import unittest
from unittest.mock import patch

from marketing_diagnosis.db_loader import DEFAULT_MYSQL_TABLES
from marketing_diagnosis.latest import normalize_dataset, process
from marketing_diagnosis.report_opening import patch_opening_html, _chart
from marketing_diagnosis.report_opening_data import _checkouts, load_opening, order_point, order_totals
from marketing_diagnosis.reporting_current import build_html, build_markdown


NOW = dt.datetime(2026, 10, 30, 16)


class Cursor:
    def __init__(self, disabled=False, missing=False, zero=False, pms_source="PMS（住哲）"):
        self.disabled, self.missing, self.zero = disabled, missing, zero
        self.pms_source = pms_source
        self.calls = []
        self.rows = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql.startswith("SHOW COLUMNS"):
            if self.missing and "jd02" in sql:
                raise RuntimeError("missing_table")
            fields = {"id", "hotel_id", "business_date", "checkin_status", "order_id", "main_checkin_id",
                      "order_source", "snapshot_time", "review_time", "review_id",
                      "metric_code", "metric_value", "metric_unit", "peer_average",
                      "competitor_rank", "competition_circle_hotel_count", "departure_date",
                      "order_status", "order_status_type", "source_platform"}
            self.rows = [{"Field": field} for field in fields]
        elif "FROM hotels" in sql:
            self.rows = [{"config_json": {"channels": ["meituan"] if self.disabled else ["meituan", "ctrip"]}}]
        elif "ROW_NUMBER()" in sql:
            self.rows = [] if self.zero else [{"order_source": "美团", "count": 2}, {"order_source": "携程", "count": 1}]
        elif sql.startswith("SELECT source_platform"):
            self.rows = [{"source_platform": self.pms_source}]
        elif "jd02" in sql:
            self.rows = [{"count": 0 if self.zero else 3}]
        elif "ctrip_ota_order_detail" in sql:
            self.rows = [{"count": 0 if self.zero else 1}]
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
        total = result["orders"]["daily_totals"][0]
        self.assertEqual((total["own_orders"], total["market_orders"], total["share"]), (15, 40, .375))
        self.assertEqual(result["orders"]["platforms"][0]["daily_points"][0]["market_orders"], 10)
        self.assertEqual(result["orders"]["platforms"][1]["daily_points"][0]["merchant_count"], 10)
        self.assertEqual(result["order_period_start"], "2026-10-23")
        self.assertEqual(result["checkout_date"], "2026-10-29")
        self.assertEqual(result["review_date"], "2026-10-30")

    def test_sql_has_exact_scope_dates_status_and_order_dedup(self):
        cursor = Cursor(pms_source="PMS（美团）")
        opening(cursor)
        checkout = next((s, p) for s, p in cursor.calls if "ROW_NUMBER()" in s)
        self.assertIn("PARTITION BY NULLIF(TRIM(main_checkin_id),'')", checkout[0])
        self.assertIn("hotel_id=%s", checkout[0])
        self.assertEqual(checkout[1][:6], ("audit", "2026-10-29", "2026-10-30", "已退房", "退房", "已结"))
        review = next((s, p) for s, p in cursor.calls if "ctrip_ota_review_detail" in s and not s.startswith("SHOW"))
        self.assertEqual(review[1][:3], ("ctrip-audit", "2026-10-30", "2026-10-31"))
        self.assertIn("COUNT(DISTINCT", review[0])
        self.assertNotIn("review_content", review[0])
        checkout = next((s, p) for s, p in cursor.calls if s.startswith("SELECT") and "FROM `ctrip_ota_order_detail`" in s)
        self.assertEqual(checkout[1][:5], ("ctrip-audit", "2026-10-29", "2026-10-30", "已过离店日期", "CheckIn"))
        orders = next((s, p) for s, p in cursor.calls if "FROM `meituan_ota_business_metrics`" in s and not s.startswith("SHOW"))
        self.assertEqual(orders[1][:3], ("audit", "2026-10-23", "2026-10-30"))

    def test_checkout_status_aliases_keep_scope_and_deduplicate_guest_rows(self):
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE jd02 (id, hotel_id, business_date, checkin_status, "
                         "order_id, order_source, snapshot_time)")
            rows = [(i, "audit", "2026-10-29", status, order, source, "2026-10-30 15:00:00")
                    for i, (status, order, source) in enumerate([
                        ("已退房", "a", "美团"), ("退房", "b", "美团"),
                        ("退房", "b", "美团"), ("退房", "c", "携程"),
                        ("已退房", "d", "携程"), ("退房", "e", "美团"),
                        ("退房", "f", "携程"), ("在住", "g", "美团"),
                        ("退房", "", "携程"),
                    ])]
            rows += [(20, "other", "2026-10-29", "退房", "x", "美团", "2026-10-30 15:00:00"),
                     (21, "audit", "2026-10-28", "退房", "y", "美团", "2026-10-30 15:00:00"),
                     (22, "audit", "2026-10-29", "退房", "z", "美团", "2026-10-30 17:00:00")]
            conn.executemany("INSERT INTO jd02 VALUES (?,?,?,?,?,?,?)", rows)

            class SqlCursor:
                def execute(self, sql, params):
                    self.cursor = conn.execute(sql.replace("%s", "?"), params)

                def fetchall(self):
                    return [dict(row) for row in self.cursor.fetchall()]

            columns = {"id", "hotel_id", "business_date", "checkin_status", "order_id",
                       "order_source", "snapshot_time"}
            with patch("marketing_diagnosis.report_opening_data._table_columns", return_value=(columns, None)):
                counts = _checkouts(SqlCursor(), "jd02", "audit", "2026-10-29", "2026-10-30", NOW)
                self.assertEqual(counts, {"total": 6, "meituan": 3, "ctrip": 3})
                conn.execute("UPDATE jd02 SET order_source='中介直连' WHERE order_id IN ('e','f')")
                counts = _checkouts(SqlCursor(), "jd02", "audit", "2026-10-29", "2026-10-30", NOW)
                self.assertEqual(counts, {"total": 6, "meituan": None, "ctrip": None})
                conn.execute("ALTER TABLE jd02 ADD COLUMN member_level")
                columns.add("member_level")
                conn.execute("UPDATE jd02 SET member_level='美团' WHERE order_id IN ('b','e','x','y','z','g','')")
                conn.execute("INSERT INTO jd02 VALUES (30,'audit','2026-10-29','退房','e',"
                             "'中介直连','2026-10-30 15:30:00',NULL)")
                counts = _checkouts(SqlCursor(), "jd02", "audit", "2026-10-29", "2026-10-30", NOW)
                # Source-only a, both-fields b and membership-only e count once each.
                self.assertEqual(counts, {"total": 6, "meituan": 3, "ctrip": None})

    def test_designated_pms_deduplicates_main_checkin_id_and_recognizes_meituan_prepaid(self):
        for source in ("PMS（美团）", "PMS（别样红）"):
            with self.subTest(source=source), sqlite3.connect(":memory:") as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("CREATE TABLE jd02 (id, hotel_id, business_date, checkin_status, order_id, "
                             "order_source, snapshot_time, member_level, main_checkin_id, source_platform)")
                def row(i, order, main, channel="中介直连", member="美团预付", **changes):
                    data = dict(id=i, hotel_id="audit", business_date="2026-10-29", checkin_status="已退房",
                                order_id=order, order_source=channel, snapshot_time="2026-10-30 15:00:00",
                                member_level=member, main_checkin_id=main, source_platform=source)
                    data.update(changes)
                    return tuple(data.values())
                conn.executemany("INSERT INTO jd02 VALUES (?,?,?,?,?,?,?,?,?,?)", [
                    row(1, None, "main-a"), row(2, None, "main-a", member=None),
                    row(3, "shared-order", "main-b", "美团"), row(4, "shared-order", "main-c", "美团"),
                    row(5, "ctrip-order", "main-d", "携程", None),
                    row(6, "order-only", "", "美团"),
                    row(7, "other", "other", hotel_id="other"),
                    row(8, "old", "old", business_date="2026-10-28"),
                    row(9, "inhouse", "inhouse", checkin_status="在住"),
                    row(10, "future", "future", snapshot_time="2026-10-30 17:00:00"),
                ])
                class SqlCursor:
                    def execute(self, sql, params):
                        self.cursor = conn.execute(sql.replace("%s", "?"), params)
                    def fetchall(self):
                        return [dict(item) for item in self.cursor.fetchall()]
                columns = {item[1] for item in conn.execute("PRAGMA table_info(jd02)")}
                with patch("marketing_diagnosis.report_opening_data._table_columns", return_value=(columns, None)):
                    counts = _checkouts(SqlCursor(), "jd02", "audit", "2026-10-29", "2026-10-30", NOW)
                    self.assertEqual(counts, {"total": 4, "meituan": 3, "ctrip": None})
                    columns.remove("main_checkin_id")
                    with self.assertRaises(ValueError):
                        _checkouts(SqlCursor(), "jd02", "audit", "2026-10-29", "2026-10-30", NOW)
                    columns.add("main_checkin_id")
                    conn.execute("UPDATE jd02 SET source_platform='PMS（住哲）'")
                    counts = _checkouts(SqlCursor(), "jd02", "audit", "2026-10-29", "2026-10-30", NOW)
                    self.assertEqual(counts, {"total": 3, "meituan": 2, "ctrip": 1})

    def test_ctrip_checkout_source_and_platform_sum_replace_pms_denominator(self):
        class OTACursor(Cursor):
            unavailable = False

            def execute(self, sql, params=()):
                super().execute(sql, params)
                if sql.startswith("SELECT") and "FROM `ctrip_ota_order_detail`" in sql:
                    if self.unavailable:
                        raise RuntimeError("ota_unavailable")
                    self.rows = [{"count": 7}]

        for source in ("PMS（美团）", "PMS（别样红）"):
            result = opening(OTACursor(pms_source=source))
            ctrip = result["reviews"]["platforms"][1]
            self.assertEqual(ctrip["checkout_orders"], 7)
            self.assertEqual(ctrip["rate"], 1 / 7)
            self.assertEqual(result["reviews"]["total"]["checkout_orders"], 9)
            self.assertEqual(result["reviews"]["total"]["rate"], 3 / 9)

        cursor = OTACursor(pms_source="PMS（住哲）")
        result = opening(cursor)
        self.assertEqual(result["reviews"]["platforms"][1]["checkout_orders"], 1)
        self.assertEqual(result["reviews"]["total"]["checkout_orders"], 3)
        self.assertFalse(any("ctrip_ota_order_detail" in sql for sql, _ in cursor.calls))

        cursor = OTACursor(pms_source="PMS（美团）")
        cursor.unavailable = True
        result = opening(cursor)
        self.assertIsNone(result["reviews"]["platforms"][1]["checkout_orders"])
        self.assertIsNone(result["reviews"]["total"]["rate"])

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
