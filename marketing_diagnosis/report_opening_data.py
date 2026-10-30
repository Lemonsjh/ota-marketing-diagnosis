"""Read-only, unscored opening metrics; only aggregate checkout/review counts."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from zoneinfo import ZoneInfo

from marketing_diagnosis.db_loader import _safe_identifier, _table_columns


PLATFORMS = ("meituan", "ctrip")


def report_time():
    return dt.datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None, microsecond=0)


def number(value):
    try:
        result = float(str(value).replace(",", ""))
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def platform_key(value):
    text = str(value or "").strip().lower()
    if any(name in text for name in ("美团", "大众点评", "meituan", "dianping")):
        return "meituan"
    if any(name in text for name in ("携程", "去哪儿", "ctrip", "qunar")):
        return "ctrip"
    return None


def _query(cursor, sql, params):
    cursor.execute(sql, tuple(params))
    return [dict(row) for row in cursor.fetchall()]


def _columns(cursor, table, required):
    columns, error = _table_columns(cursor, table)
    if error or not set(required).issubset(columns):
        raise ValueError("required_source_unavailable")
    return columns


def _enabled(cursor, hotel_id, requested, diagnostics):
    try:
        rows = _query(cursor, "SELECT config_json FROM hotels WHERE hotel_id=%s LIMIT 1", [hotel_id])
        config = rows[0]["config_json"]
        config = json.loads(config) if isinstance(config, str) else config
        channels = config.get("channels", config.get("enabled_channels"))
        if channels is None:
            raise ValueError("channel_config_missing")
        if isinstance(channels, str):
            channels = channels.replace("，", ",").split(",")
        if isinstance(channels, dict):
            channels = [key for key, value in channels.items() if value]
        enabled = {platform_key(channel) for channel in channels}
        return [platform for platform in requested if platform in enabled]
    except Exception:
        diagnostics.append("ota_channel_config_unavailable")
        return list(requested)


def _checkouts(cursor, table, hotel_id, yesterday, today, now):
    columns = _columns(cursor, table, {"hotel_id", "business_date", "checkin_status", "order_id"})
    where = "hotel_id=%s AND business_date>=%s AND business_date<%s AND checkin_status=%s"
    params = [hotel_id, yesterday, today, "已退房"]
    if "snapshot_time" in columns:
        where += " AND snapshot_time<=%s"
        params.append(str(now))
    valid_order = "NULLIF(TRIM(order_id),'')"
    total = _query(cursor, f"SELECT COUNT(DISTINCT {valid_order}) AS count FROM {_safe_identifier(table)} WHERE {where}", params)[0]["count"]
    counts = {platform: None for platform in PLATFORMS}
    if "order_source" in columns:
        # One order may have several guest rows. Pick its latest source without
        # exporting names, order IDs or any accommodation detail to the report.
        order = "snapshot_time DESC, id DESC" if "id" in columns and "snapshot_time" in columns else "order_id"
        rows = _query(cursor,
            "SELECT order_source, COUNT(*) AS count FROM ("
            f"SELECT order_source, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY {order}) AS rn "
            f"FROM {_safe_identifier(table)} WHERE {where} AND {valid_order} IS NOT NULL"
            ") AS stays WHERE rn=1 GROUP BY order_source", params)
        counts = dict.fromkeys(PLATFORMS, 0)
        for row in rows:
            platform = platform_key(row["order_source"])
            if platform:
                counts[platform] += int(row["count"])
    return {"total": int(total), **counts}


def _reviews(cursor, table, hotel_id, today, tomorrow, now):
    columns = _columns(cursor, table, {"hotel_id", "review_time"})
    count = "COUNT(*)"
    if {"review_id", "id"}.issubset(columns):
        count = "COUNT(DISTINCT COALESCE(NULLIF(TRIM(review_id),''),CONCAT('row:',id)))"
    where = "hotel_id=%s AND review_time>=%s AND review_time<%s AND review_time<=%s"
    params = [hotel_id, today, tomorrow, str(now)]
    if "snapshot_time" in columns:
        where += " AND snapshot_time<=%s"
        params.append(str(now))
    return int(_query(cursor, f"SELECT {count} AS count FROM {_safe_identifier(table)} WHERE {where}", params)[0]["count"])


def _rank_count(value):
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(value or ""))
    return int(match[2]) if match and 1 <= int(match[1]) <= int(match[2]) else None


def _circle_count(cursor, table, hotel_id, now):
    _columns(cursor, table, {"hotel_id", "snapshot_time", "competition_circle_hotel_count"})
    rows = _query(cursor,
        f"SELECT competition_circle_hotel_count FROM {_safe_identifier(table)} "
        "WHERE hotel_id=%s AND metric_code=%s AND snapshot_time<=%s ORDER BY snapshot_time DESC LIMIT 1",
        [hotel_id, "booking_order_count", str(now)])
    count = number(rows[0].get("competition_circle_hotel_count")) if rows else None
    return int(count) if count and count.is_integer() else None


def order_point(rows, platform, count=None):
    code = "PAY_ORDER_CNT" if platform == "meituan" else "booking_order_count"
    row = next((row for row in rows if row.get("metric_code") == code), {})
    batch = [item for item in rows if item.get("snapshot_time") == row.get("snapshot_time")]
    own = number(row.get("metric_value"))
    peer = number(row.get("peer_average"))
    if platform == "meituan":
        fallback = next((item for item in batch if item.get("metric_code") == "FLOW_PAY_ORDER_CNT"), {})
        own = own if own is not None else number(fallback.get("metric_value"))
        peer = peer if peer is not None else number(fallback.get("peer_average"))
    count = _rank_count(row.get("competitor_rank")) or count
    if count is None:
        counts = {_rank_count(item.get("competitor_rank")) for item in batch} - {None}
        count = next(iter(counts)) if len(counts) == 1 else None
    # This opening panel uses the requested merchant-count × peer-average formula.
    market = peer * count if peer is not None and count else None
    return {"platform": platform, "own_orders": own, "peer_average": peer,
            "merchant_count": count, "market_orders": market,
            "share": own / market if own is not None and market else None,
            "snapshot_time": str(row.get("snapshot_time") or "")}


def _orders(cursor, table, hotel_id, start, today, now, platform, circle_table):
    _columns(cursor, table, {"hotel_id", "business_date", "snapshot_time", "metric_code",
                             "metric_value", "metric_unit", "peer_average", "competitor_rank"})
    rows = _query(cursor,
        "SELECT business_date,metric_code,metric_value,metric_unit,peer_average,competitor_rank,snapshot_time "
        f"FROM {_safe_identifier(table)} WHERE hotel_id=%s AND business_date>=%s "
        "AND business_date<%s AND snapshot_time<=%s ORDER BY snapshot_time DESC",
        [hotel_id, start, today, str(now)])
    code = "PAY_ORDER_CNT" if platform == "meituan" else "booking_order_count"
    units = {"单", "order", "orders"}
    rows = [row for row in rows if str(row.get("metric_unit") or "").lower() in units or row.get("metric_code") != code]
    count = None
    if platform == "ctrip" and not _rank_count(next((r.get("competitor_rank") for r in rows if r.get("metric_code") == code), None)):
        try:
            count = _circle_count(cursor, circle_table, hotel_id, now)
        except Exception:
            pass
    days = {}
    for row in rows:
        days.setdefault(str(row["business_date"])[:10], []).append(row)
    return [{"business_date": day, **order_point(batch, platform, count)}
            for day, batch in sorted(days.items())
            if any(row.get("metric_code") == code for row in batch)]


def _sum(values):
    return sum(values) if values and all(value is not None for value in values) else None


def order_totals(platforms):
    days = {}
    for platform in platforms:
        for point in platform["daily_points"]:
            days.setdefault(point["business_date"], []).append(point)
    totals = []
    for day, points in sorted(days.items()):
        own = _sum([point["own_orders"] for point in points])
        market = _sum([point["market_orders"] for point in points])
        totals.append({"business_date": day, "own_orders": own, "market_orders": market,
                       "share": own / market if own is not None and market else None,
                       "platforms": [point["platform"] for point in points]})
    return totals


def load_opening(cursor, tables, hotel_id, ctrip_hotel_id, requested):
    now = report_time()
    today = now.date().isoformat()
    yesterday = (now.date() - dt.timedelta(days=1)).isoformat()
    order_start = (now.date() - dt.timedelta(days=7)).isoformat()
    tomorrow = (now.date() + dt.timedelta(days=1)).isoformat()
    diagnostics = []
    platforms = _enabled(cursor, hotel_id, requested, diagnostics)
    checkouts = dict.fromkeys(("total", *PLATFORMS))
    try:
        checkouts = _checkouts(cursor, tables.get("guest_stay_detail", "jd02_guest_stay_detail"), hotel_id, yesterday, today, now)
    except Exception as exc:
        diagnostics.append("checkouts_unavailable:" + type(exc).__name__)
    reviews, orders = [], []
    for platform in platforms:
        scoped_id = ctrip_hotel_id if platform == "ctrip" else hotel_id
        count = None
        try:
            count = _reviews(cursor, tables[f"{platform}_reviews"], scoped_id, today, tomorrow, now)
        except Exception as exc:
            diagnostics.append(platform + "_reviews_unavailable:" + type(exc).__name__)
        denominator = checkouts[platform]
        reviews.append({"platform": platform, "review_count": count, "checkout_orders": denominator,
                        "rate": count / denominator if count is not None and denominator else None})
        try:
            points = _orders(cursor, tables[f"{platform}_funnel"], scoped_id, order_start, today, now, platform,
                            tables.get("ctrip_competition_metrics_30d", "ctrip_ota_competition_metrics_30d"))
        except Exception as exc:
            diagnostics.append(platform + "_orders_unavailable:" + type(exc).__name__)
            points = []
        orders.append({"platform": platform, "daily_points": points})
    review_total = _sum([row["review_count"] for row in reviews])
    return {"as_of": str(now), "checkout_date": yesterday, "review_date": today,
            "order_period_start": order_start, "order_period_end": yesterday, "participates_in_score": False,
            "reviews": {"platforms": reviews, "total": {"review_count": review_total,
                "checkout_orders": checkouts["total"],
                "rate": review_total / checkouts["total"] if review_total is not None and checkouts["total"] else None}},
            "orders": {"platforms": orders, "daily_totals": order_totals(orders)},
            "diagnostics": diagnostics}
