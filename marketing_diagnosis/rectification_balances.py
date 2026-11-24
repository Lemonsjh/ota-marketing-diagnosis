"""Read promotion account snapshots for the rectification plan."""

from marketing_diagnosis.report_opening_data import _query, report_time


PROMOTION_TYPES = {"meituan": "promotion_tong", "ctrip": "pyramid"}


def load_promotion_balances(cursor, hotel_id, enabled_channels):
    balances = {}
    if not hotel_id:
        return balances
    as_of = report_time()
    for channel in enabled_channels:
        try:
            rows = _query(cursor, """
                SELECT total_balance, currency, snapshot_time
                FROM ota_promotion_balance
                WHERE hotel_id = %s AND platform_scope = %s AND promotion_type = %s
                  AND snapshot_time <= %s
                ORDER BY snapshot_time DESC LIMIT 1
            """, (hotel_id, channel, PROMOTION_TYPES[channel], as_of))
        except Exception:
            # This optional source can be absent for hotels without a balance collector.
            continue
        if rows and rows[0]["total_balance"] is not None:
            row = rows[0]
            balances[channel] = {
                "total_balance": str(row["total_balance"]),
                "currency": row.get("currency"),
                "snapshot_time": str(row["snapshot_time"]),
            }
    return balances
