"""Meituan item 03: yesterday's room-night share and seven fixed daily points."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

METRIC_CODE = "CONSUME_ROOMNIGHT_SPLIT_EX_7DAYS_REFUND"
TITLE = "大盘入住间夜与本店份额"
DESCRIPTION = "展示昨日本店入住间夜大盘份额及截至昨日的过去7天每日份额趋势。"
SECTION = "meituan_market_room_nights"


def report_time() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def _stamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _point(row: dict[str, Any], day: str) -> dict[str, Any]:
    result = {"business_date": day, "own_room_nights": None, "peer_average": None,
              "hotel_count": None, "rank": None, "market_room_nights": None,
              "share": None, "reason": "missing"}
    if not row:
        return result
    stamp = _stamp(row.get("snapshot_time"))
    if stamp is None or stamp.date().isoformat() <= day:
        return {**result, "reason": "unfinished"}
    if (row.get("metric_unit") or "间夜") not in {"间夜", "room_night", "room_nights"}:
        return {**result, "reason": "invalid_unit"}
    own, peer = number(row.get("metric_value")), number(row.get("peer_average"))
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(row.get("competitor_rank") or ""))
    rank, count = (int(match[1]), int(match[2])) if match else (None, None)
    if count is not None and not 1 <= rank <= count:
        rank, count = None, None
    result.update(own_room_nights=own, peer_average=peer, hotel_count=count, rank=rank)
    if own is None or peer is None or count is None:
        return {**result, "reason": "incomplete"}
    total = own + peer * (count - 1)
    return {**result, "market_room_nights": total,
            "share": own / total if total > 0 else None,
            "reason": "ok" if total > 0 else "zero_market"}


def patch_market_share(result: dict[str, Any], sections: dict[str, Any], *,
                       hotel_id: str | None = None, as_of: datetime | None = None) -> dict[str, Any]:
    from marketing_diagnosis.meituan_exposure_monthly import _find_item, _refresh_summary

    item = _find_item((result.get("visual_diagnosis") or {}).get("items"), 3)
    if item is None:
        return result
    now = as_of or report_time()
    days = [(now.date() - timedelta(days=offset)).isoformat() for offset in range(7, 0, -1)]
    rows = [row for row in sections.get(SECTION, []) if isinstance(row, dict)
            and row.get("metric_code") == METRIC_CODE]
    hotel_ids = {str(row.get("hotel_id")) for row in rows if row.get("hotel_id")}
    scope = str(hotel_id) if hotel_id else next(iter(hotel_ids)) if len(hotel_ids) == 1 else None
    latest: dict[str, Any] = {}
    for row in rows:
        day = str(row.get("business_date") or "")[:10]
        stamp = _stamp(row.get("snapshot_time"))
        if not scope or str(row.get("hotel_id") or "") != scope or day not in days or stamp is None or stamp > now:
            continue
        previous = latest.get(day)
        if previous is None or (stamp, int(row.get("id") or 0)) > (_stamp(previous.get("snapshot_time")), int(previous.get("id") or 0)):
            latest[day] = row
    points = [_point(latest.get(day, {}), day) for day in days]
    yesterday = points[-1]
    item.update({
        "item_name": TITLE, "data_status": "pending_rule" if yesterday["share"] is not None else "missing",
        "score_ratio": None, "item_score": None,
        "fields": [{"label": "昨日本店大盘份额", "value": f"{yesterday['share']:.2%}" if yesterday["share"] is not None else "待更新"},
                   {"label": "本店入住间夜", "value": yesterday["own_room_nights"]},
                   {"label": "大盘入住间夜（估算）", "value": yesterday["market_room_nights"]}],
        "records": list(latest.values()), "market_share": {"yesterday": yesterday, "daily_points": points},
        "source_table": "meituan_ota_business_metrics",
        "source_fields": ["business_date", "metric_code", "metric_value", "peer_average", "competitor_rank", "snapshot_time"],
        "note": DESCRIPTION + " 按入住间夜估算，不等同于全店出租率或订单份额；评分规则待确认。",
    })
    _refresh_summary(result["visual_diagnosis"])
    return result
