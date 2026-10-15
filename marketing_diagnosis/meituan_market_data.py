"""Exact hotel/metric/date query for report item 03; never load other tenants."""
from datetime import timedelta

from marketing_diagnosis.meituan_market_share import METRIC_CODE, report_time


def fetch_market_rows(cursor, table, hotel_id):
    from marketing_diagnosis.db_loader import _fetch, _table_columns

    columns, error = _table_columns(cursor, table)
    required = {"hotel_id", "business_date", "snapshot_time", "metric_code",
                "metric_value", "peer_average", "competitor_rank"}
    if error or not hotel_id or required - columns:
        return [], {"table": table, "status": "error", "rows": 0,
                    "error": "market_scope_or_required_columns_missing"}
    now = report_time()
    start, end = (now.date() - timedelta(days=7)).isoformat(), (now.date() - timedelta(days=1)).isoformat()
    where = "hotel_id=%s AND metric_code=%s AND business_date>=%s AND business_date<%s AND snapshot_time<=%s"
    rows, diag = _fetch(cursor, table, 5000, where,
                        [hotel_id, METRIC_CODE, start, now.date().isoformat(), str(now)],
                        "business_date DESC, snapshot_time DESC" + (", id DESC" if "id" in columns else ""))
    return rows, {**diag, "target_start": start, "target_end": end, "hotel_filter_applied": True}
