from __future__ import annotations

from typing import Any

from marketing_diagnosis.ctrip_flow_rank_rules import build_flow_item
from marketing_diagnosis.ctrip_rights_data import build_rights_item
from marketing_diagnosis.ctrip_score_alignment import align_ctrip_scores
from marketing_diagnosis.ctrip_configuration_v63 import _business_item
from marketing_diagnosis.meituan_market_share import patch_market_share
from marketing_diagnosis.meituan_recent_reviews import attach_recent_reviews
from marketing_diagnosis.rules_v5 import _refresh_ctrip_summary
from marketing_diagnosis.rules_v5 import process as upstream_process


_INACTIVE_POINTS_STATES = {"未报名", "未参与"}


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _psi_information_completeness(sections: dict[str, Any]) -> float | None:
    rows = [
        row
        for row in sections.get("ctrip_psi_metric") or []
        if isinstance(row, dict)
        and str(row.get("metric_code") or "").strip().lower() == "information_completeness"
        and _number(row.get("metric_value")) is not None
    ]
    if not rows:
        return None
    latest = max(
        rows,
        key=lambda row: str(
            row.get("snapshot_time") or row.get("updated_at") or row.get("created_at") or ""
        ),
    )
    return _number(latest.get("metric_value"))


def _fallback_information_completeness(items: dict[str, Any], sections: dict[str, Any]) -> None:
    """Use PSI's same metric only when the dedicated status snapshot has no value."""
    item = items.get("8") or items.get(8)
    if not isinstance(item, dict) or item.get("item_score") is not None:
        return
    completeness = _psi_information_completeness(sections)
    if completeness is None:
        return

    display = f"{completeness:g}%"
    item["item_score"] = 4.0 if completeness >= 100 else 0.0
    item["data_status"] = "success"
    item["fields"] = [
        {"label": "信息完整度", "value": display, "note": ""},
        {"label": "完整度结果", "value": "已达标" if completeness >= 100 else "未达标", "note": ""},
    ]
    item["note"] = "信息完整度达到100得4分，低于100得0分。"


def _normalize_points_alliance_fields(items: dict[str, Any]) -> None:
    """Keep item 14 to the defined order-based, non-revenue presentation."""
    item = items.get("14") or items.get(14)
    if not isinstance(item, dict):
        return

    normalized = []
    for field in item.get("fields") or []:
        if not isinstance(field, dict):
            continue
        label = str(field.get("label") or "").strip()
        if label == "成交金额":
            continue
        if label == "近30天订单" and field.get("value") in (None, ""):
            field = {**field, "value": 0}
        normalized.append(field)
    item["fields"] = normalized


def _zero_inactive_points_metrics(items: dict[str, Any]) -> None:
    item = items.get("14") or items.get(14)
    if not isinstance(item, dict):
        return

    fields = [field for field in item.get("fields") or [] if isinstance(field, dict)]
    status = next(
        (
            str(field.get("value") or "").strip()
            for field in fields
            if str(field.get("label") or "").strip() in {"报名状态", "参与状态"}
        ),
        "",
    )
    if status not in _INACTIVE_POINTS_STATES:
        return

    for field in fields:
        if str(field.get("label") or "").strip() == "近30天订单":
            field["value"] = 0
    item["item_score"] = 0.0
    item["data_status"] = "success"


def _patch_business_travel(items: dict[str, Any], sections: dict[str, Any]) -> None:
    """Match participation by activity name; retain the existing two-point rule."""
    activity = next((row for row in sections.get("ctrip_promotion_activity") or []
                     if isinstance(row, dict) and str(row.get("activity_name") or "").strip() == "商旅专享"), None)
    status = next((row for row in sections.get("ctrip_promotion_status") or []
                   if isinstance(row, dict) and str(row.get("activity_code") or "").strip().lower() == "business_travel_price"), {})
    performance = next((row for row in sections.get("ctrip_promotion_activity_performance") or []
                        if isinstance(row, dict) and str(row.get("campaign_name") or "").strip() == "商旅专享"), {})
    joined = activity is not None
    item = _business_item({
        "status": "JOINED" if joined else "NOT_JOINED", "enabled": int(joined),
        "room_type_count": status.get("room_type_count"),
        "orders_30d": performance.get("campaign_quantity"),
        "metric_value": performance.get("campaign_gmv"),
    })
    item["source"] = "ctrip_ota_promotion_activity / ctrip_ota_promotion_activity_performance / ctrip_ota_promotion_status"
    item["fields"] = [
        {"label": "参与状态", "value": "已参与" if joined else "未参与", "note": ""},
        {"label": "近30天订单", "value": performance.get("campaign_quantity") if joined else 0, "note": ""},
        {"label": "成交金额", "value": performance.get("campaign_gmv") if joined else 0, "note": ""},
    ]
    item["note"] = (
        "在最新活动列表中匹配到“商旅专享”，判为已参与；订单及金额来自同名活动效果。"
        "本项满分2分，订单量及成交金额仅作展示。"
        if joined else "最新活动列表未匹配到“商旅专享”，本项按未参与计0分。"
    )
    items["16"] = item


def process(data: dict[str, Any]) -> dict[str, Any]:
    """Apply final Ctrip rule corrections after the established rule pipeline."""

    result = upstream_process(data)
    sections = data.get("sections") or {}
    patch_market_share(result, sections, hotel_id=data.get("hotel_id"))
    attach_recent_reviews(result, data)
    items = result.setdefault("ctrip_items", {})

    existing_flow = items.get("3") or items.get(3)
    items["3"] = build_flow_item(
        sections,
        existing_flow if isinstance(existing_flow, dict) else None,
    )

    existing_rights = items.get("13") or items.get(13)
    items["13"] = build_rights_item(
        sections,
        existing_rights if isinstance(existing_rights, dict) else None,
    )

    _normalize_points_alliance_fields(items)
    _zero_inactive_points_metrics(items)
    _patch_business_travel(items, sections)
    _fallback_information_completeness(items, sections)
    align_ctrip_scores(result, sections)
    _refresh_ctrip_summary(result)
    return result


__all__ = ["process"]
