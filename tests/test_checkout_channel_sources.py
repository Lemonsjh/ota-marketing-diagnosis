import sqlite3
import unittest
from unittest.mock import patch

from marketing_diagnosis.report_opening_data import _checkouts


class CheckoutChannelSourceTests(unittest.TestCase):
    def test_guest_source_recognizes_both_channels_without_duplicate_orders(self):
        for pms in ("PMS（美团）", "PMS（别样红）", "PMS（住哲）"):
            with self.subTest(pms=pms), sqlite3.connect(":memory:") as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("CREATE TABLE jd02 (id, hotel_id, business_date, checkin_status, "
                             "order_id, main_checkin_id, order_source, guest_source, member_level, "
                             "source_platform, snapshot_time)")
                def row(i, key, order_source, guest_source, member=None, **changes):
                    values = dict(id=i, hotel_id="audit", business_date="2026-11-05",
                                  checkin_status="已退房", order_id=key, main_checkin_id=key,
                                  order_source=order_source, guest_source=guest_source,
                                  member_level=member, source_platform=pms,
                                  snapshot_time="2026-11-06 10:00:00")
                    values.update(changes)
                    return tuple(values.values())
                conn.executemany("INSERT INTO jd02 VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
                    row(1, "a", "中介直连", "美团", checkin_status="已结"),
                    row(2, "b", "美团", "meituan", "美团预付"),
                    row(3, "b", "美团", "meituan", "美团预付", checkin_status="已结"),
                    row(4, "c", "中介直连", "携程", checkin_status="已结"),
                    row(5, "d", "qunar", "去哪儿", checkin_status="退房"),
                    row(6, "other", "美团", "美团", hotel_id="other"),
                    row(7, "old", "美团", "美团", business_date="2026-11-04"),
                    row(8, "inhouse", "美团", "美团", checkin_status="在住"),
                    row(9, "future", "美团", "美团", snapshot_time="2026-11-06 13:00:00"),
                    row(10, "", "美团", "美团"),
                    row(11, "unsettled", "美团", "美团", checkin_status="未结"),
                ])
                class Cursor:
                    def execute(self, sql, params):
                        self.cursor = conn.execute(sql.replace("%s", "?"), params)
                    def fetchall(self):
                        return [dict(item) for item in self.cursor.fetchall()]
                columns = {item[1] for item in conn.execute("PRAGMA table_info(jd02)")}
                # Also support schemas where guest_source is the only channel field.
                for channel_columns in (columns, columns - {"order_source", "member_level"}):
                    with self.subTest(columns=sorted(channel_columns)), patch(
                        "marketing_diagnosis.report_opening_data._table_columns",
                        return_value=(channel_columns, None),
                    ):
                        result = _checkouts(Cursor(), "jd02", "audit", "2026-11-05",
                                            "2026-11-06", "2026-11-06 12:00:00")
                        self.assertEqual(result, {"meituan": 2, "ctrip": 2})


if __name__ == "__main__":
    unittest.main()
