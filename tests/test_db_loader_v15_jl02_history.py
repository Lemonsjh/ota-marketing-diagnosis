from __future__ import annotations

import unittest
import sqlite3
from unittest.mock import patch

from marketing_diagnosis import db_loader_v9, db_loader_v15
from marketing_diagnosis.db_loader_v15 import (
    _jl02_history_start,
    _load_jl02_history,
)


class _FakeCursor:
    def __init__(self):
        self.mode = ""
        self.executed: list[tuple[str, list]] = []

    def execute(self, sql, params=None):
        values = list(params or [])
        self.executed.append((sql, values))
        if sql.startswith("SHOW COLUMNS"):
            self.mode = "columns"
        elif "MAX(DATE(`business_date`))" in sql:
            self.mode = "latest"
        else:
            self.mode = "rows"

    def fetchone(self):
        if self.mode == "latest":
            return {"latest_business_date": "2026-07-16"}
        return None

    def fetchall(self):
        if self.mode == "columns":
            return [
                {"Field": "hotel_id"},
                {"Field": "business_date"},
                {"Field": "category"},
                {"Field": "room_type_id"},
                {"Field": "metric_name"},
                {"Field": "value_month"},
                {"Field": "snapshot_time"},
            ]
        if self.mode == "rows":
            return [
                {
                    "hotel_id": "puyue",
                    "business_date": "2025-05-31",
                    "category": "总营业指标",
                    "room_type_id": None,
                    "metric_name": "房费",
                    "value_month": 136778.15,
                    "snapshot_time": "2025-05-31 23:59:59",
                },
                {
                    "hotel_id": "puyue",
                    "business_date": "2026-07-16",
                    "category": "总营业指标",
                    "room_type_id": None,
                    "metric_name": "房费",
                    "value_month": 69076.50,
                    "snapshot_time": "2026-07-16 23:59:59",
                },
            ]
        return []


class JL02HistoryLoaderV15Tests(unittest.TestCase):
    def test_total_room_revenue_survives_sql_filter_and_reaches_trend(self):
        from marketing_diagnosis.performance_yoy_v40 import patch_performance_yoy
        from marketing_diagnosis.reporting_v37 import _performance_card

        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE jl02 (hotel_id, business_date, category, metric_name, value_month)")
            rows = [("licheng", day, "总营业指标", "总房费", value) for day, value in (
                ("2026-09-30", 0), ("2026-10-31", 27625.34), ("2026-11-01", 1079.4),
                ("2025-09-30", 0), ("2025-10-31", 0), ("2025-11-01", 0),
            )]
            rows += [("other", "2026-11-01", "总营业指标", "总房费", 99999),
                     ("licheng", "2026-11-01", "总营业指标", "门店总收入", 88888)]
            conn.executemany("INSERT INTO jl02 VALUES (?,?,?,?,?)", rows)

            class Cursor:
                def execute(self, sql, params):
                    self.cursor = conn.execute(sql.replace("%s", "?"), params)

                def fetchone(self):
                    row = self.cursor.fetchone()
                    return dict(row) if row is not None else None

                def fetchall(self):
                    return [dict(row) for row in self.cursor.fetchall()]

            columns = {"hotel_id", "business_date", "category", "metric_name", "value_month"}
            with patch.object(db_loader_v15.base, "_table_columns", return_value=(columns, None)):
                loaded, diag = _load_jl02_history(Cursor(), "jl02", 5000, "licheng", "2026-11-02")
            self.assertEqual(diag["status"], "ok")
            self.assertEqual(len(loaded), 6)
            self.assertTrue(all(row["hotel_id"] == "licheng" for row in loaded))
            result = {"items": [{"standard_item_id": 1, "base_score": 10}]}
            patch_performance_yoy(result, {"hotel_performance_daily": loaded})
            item = result["items"][0]
            revenue = [next(m for m in p["metrics"] if m["key"] == "revenue")
                       for p in item["trend_periods"]]
            self.assertEqual([m["current"] for m in revenue], [0, 27625.34, 1079.4])
            self.assertEqual([m["previous"] for m in revenue], [0, 0, 0])
            self.assertTrue(all(m["yoy"] is None for m in revenue))
            self.assertIsNone(item["item_score"])
            html = _performance_card(item)
            self.assertIn("27,625.34", html)
            self.assertIn("1,079.40", html)

    def test_history_starts_at_prior_year_of_oldest_display_month(self):
        self.assertEqual(_jl02_history_start("2026-07-16"), "2025-05-01")
        self.assertEqual(_jl02_history_start("2026-01-31"), "2024-11-01")

    def test_query_includes_complete_prior_year_comparison_window(self):
        cursor = _FakeCursor()
        rows, diag = _load_jl02_history(
            cursor,
            "jl02_hotel_performance_daily",
            5000,
            "puyue",
            "2026-07-16",
        )

        self.assertEqual(diag["history_start"], "2025-05-01")
        self.assertEqual(diag["history_end"], "2026-07-16")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["business_date"], "2025-05-31")

        history_sql, history_params = cursor.executed[-1]
        self.assertIn("DATE(`business_date`) >= %s", history_sql)
        self.assertIn("DATE(`business_date`) <= %s", history_sql)
        self.assertIn("`category` = %s", history_sql)
        self.assertIn("(`room_type_id` IS NULL OR `room_type_id` = '')", history_sql)
        self.assertIn("2025-05-01", history_params)
        self.assertIn("2026-07-16", history_params)
        self.assertIn("总营业指标", history_params)

    def test_runtime_compatibility_loader_routes_to_v15(self):
        self.assertIs(
            db_loader_v9.load_mysql_dsn_dataset,
            db_loader_v15.load_mysql_dsn_dataset,
        )


if __name__ == "__main__":
    unittest.main()
