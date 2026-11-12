"""Read-only, unscored opening metrics; only aggregate checkout/review counts."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from zoneinfo import ZoneInfo

from marketing_diagnosis.db_loader import _safe_identifier, _table_columns
from marketing_diagnosis.meituan_market_share import market_room_nights


CTRIP_ROOM_NIGHTS = "inhouse_room_night"


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


def _ota_checkouts(cursor, table, platform, hotel_id, yesterday, today, now):
    required = {"hotel_id", "order_id", "departure_date", "order_status"}
    if platform == "ctrip":
        required.add("order_status_type")
    columns = _columns(cursor, table, required)
    where = "hotel_id=%s AND departure_date>=%s AND departure_date<%s AND order_status=%s"
    status = "已过离店日期" if platform == "ctrip" else "CONSUMED"
    params = [hotel_id, yesterday, today, status]
    if platform == "ctrip":
        where += " AND order_status_type=%s"
        params.append("CheckIn")
    if "snapshot_time" in columns:
        where += " AND snapshot_time<=%s"
        params.append(str(now))
    rows = _query(cursor, f"SELECT COUNT(DISTINCT NULLIF(TRIM(order_id),'')) AS count "
                  f"FROM {_safe_identifier(table)} WHERE {where}", params)
    return int(rows[0]["count"])


def _reviews(cursor, table, hotel_id, yesterday, today, now):
    columns = _columns(cursor, table, {"hotel_id", "review_time"})
    count = "COUNT(*)"
    if {"review_id", "id"}.issubset(columns):
        count = "COUNT(DISTINCT COALESCE(NULLIF(TRIM(review_id),''),CONCAT('row:',id)))"
    where = "hotel_id=%s AND review_time>=%s AND review_time<%s"
    params = [hotel_id, yesterday, today]
    if "snapshot_time" in columns:
        where += " AND snapshot_time<=%s"
        params.append(str(now))
    return int(_query(cursor, f"SELECT {count} AS count FROM {_safe_identifier(table)} WHERE {where}", params)[0]["count"])


def _rank_count(value):
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(value or ""))
    return int(match[2]) if match and 1 <= int(match[1]) <= int(match[2]) else None


def _circle_count(cursor, table, hotel_id, now):
    _columns(cursor, table, {"hotel_id", "metric_code", "snapshot_time", "competition_circle_hotel_count"})
    rows = _query(cursor,
        f"SELECT competition_circle_hotel_count FROM {_safe_identifier(table)} "
        "WHERE hotel_id=%s AND metric_code=%s AND snapshot_time<=%s ORDER BY snapshot_time DESC LIMIT 1",
        [hotel_id, CTRIP_ROOM_NIGHTS, str(now)])
    count = number(rows[0].get("competition_circle_hotel_count")) if rows else None
    return int(count) if count and count.is_integer() else None


def _ctrip_room_nights(cursor, table, hotel_id, start, today, now, circle_table):
    columns = _columns(cursor, table, {"hotel_id", "business_date", "snapshot_time", "metric_code",
                                       "metric_value", "metric_unit", "peer_average", "competitor_rank"})
    order = "snapshot_time DESC" + (", id DESC" if "id" in columns else "")
    rows = _query(cursor,
        "SELECT business_date,metric_value,metric_unit,peer_average,competitor_rank,snapshot_time "
        f"FROM {_safe_identifier(table)} WHERE hotel_id=%s AND business_date>=%s "
        f"AND business_date<%s AND metric_code=%s AND snapshot_time<=%s ORDER BY {order}",
        [hotel_id, start, today, CTRIP_ROOM_NIGHTS, str(now)])
    days = {}
    for row in rows:
        day = str(row["business_date"])[:10]
        if str(row["snapshot_time"])[:10] > day and row["metric_unit"] in {"间夜", "room_night", "room_nights"}:
            days.setdefault(day, row)
    circle_count = None
    if any(_rank_count(row["competitor_rank"]) is None for row in days.values()):
        try:
            circle_count = _circle_count(cursor, circle_table, hotel_id, now)
        except Exception:
            pass
    points = []
    for day, row in sorted(days.items()):
        own, peer = number(row["metric_value"]), number(row["peer_average"])
        count = _rank_count(row["competitor_rank"]) or circle_count
        market = peer * count if peer is not None and count else None
        points.append({"business_date": day, "own_room_nights": own, "market_room_nights": market,
                       "hotel_count": count, "share": own / market if own is not None and market else None})
    return points


def _sum(values):
    return sum(values) if values and all(value is not None for value in values) else None


def room_night_totals(platforms):
    days = {}
    for platform in platforms:
        for point in platform["daily_points"]:
            days.setdefault(point["business_date"], []).append((platform["platform"], point))
    totals = []
    for day, points in sorted(days.items()):
        own = _sum([point["own_room_nights"] for _, point in points])
        market = _sum([point["market_room_nights"] for _, point in points])
        totals.append({"business_date": day, "own_room_nights": own, "market_room_nights": market,
                       "share": own / market if own is not None and market else None,
                       "platforms": [platform for platform, _ in points]})
    return totals


def load_opening(cursor, tables, hotel_id, ctrip_hotel_id, requested, *, meituan_rows=()):
    now = report_time()
    today = now.date().isoformat()
    yesterday = (now.date() - dt.timedelta(days=1)).isoformat()
    nights_start = (now.date() - dt.timedelta(days=7)).isoformat()
    diagnostics = []
    platforms = _enabled(cursor, hotel_id, requested, diagnostics)
    reviews, room_nights = [], []
    for platform in platforms:
        scoped_id = ctrip_hotel_id if platform == "ctrip" else hotel_id
        count = None
        try:
            count = _reviews(cursor, tables[f"{platform}_reviews"], scoped_id, yesterday, today, now)
        except Exception as exc:
            diagnostics.append(platform + "_reviews_unavailable:" + type(exc).__name__)
        denominator = None
        try:
            table = tables.get(f"{platform}_order_detail", f"{platform}_ota_order_detail")
            denominator = _ota_checkouts(cursor, table, platform, scoped_id, yesterday, today, now)
        except Exception as exc:
            diagnostics.append(platform + "_checkouts_unavailable:" + type(exc).__name__)
        reviews.append({"platform": platform, "review_count": count, "checkout_orders": denominator,
                        "rate": count / denominator if count is not None and denominator else None})
        if platform == "meituan":
            points, _ = market_room_nights(meituan_rows, scoped_id, now)
            points = [point for point in points if point["own_room_nights"] is not None]
        else:
            try:
                points = _ctrip_room_nights(cursor, tables["ctrip_funnel"], scoped_id, nights_start, today, now,
                    tables.get("ctrip_competition_metrics_30d", "ctrip_ota_competition_metrics_30d"))
            except Exception as exc:
                diagnostics.append("ctrip_room_nights_unavailable:" + type(exc).__name__)
                points = []
        room_nights.append({"platform": platform, "daily_points": points})
    review_total = _sum([row["review_count"] for row in reviews])
    checkout_total = _sum([row["checkout_orders"] for row in reviews])
    return {"as_of": str(now), "checkout_date": yesterday, "review_date": yesterday,
            "participates_in_score": False,
            "reviews": {"platforms": reviews, "total": {"review_count": review_total,
                "checkout_orders": checkout_total,
                "rate": review_total / checkout_total if review_total is not None and checkout_total else None}},
            "room_nights": {"period_start": nights_start, "period_end": yesterday,
                            "platforms": room_nights, "daily_totals": room_night_totals(room_nights)},
            "diagnostics": diagnostics}
