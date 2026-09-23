from __future__ import annotations

import copy
import re
from typing import Any


_CTRIP_YOYO_ACTIVITY_NAMES = {"YOYO卡&扫码住专享促销", "YOYO卡&扫码住专享红包"}
_CTRIP_YOYO_PROMOTION_CAMPAIGN = "YOYO卡&扫码住专享促销"
_FLASH_STAY_CODE = "quick_check_inn"
_FLASH_STAY_NAME = "闪住"
_CTRIP_VIDEO_TYPES = (
    ("hotel_detail_video", "详情页视频"),
    ("hotel_listing_video", "列表页视频"),
    ("room_type_video", "房型视频"),
)
_LISTING_CONTENT_CODES = (
    ("listing_recommendation_words", "推荐词"),
    ("listing_short_tags", "短标签"),
)
_ROOM_NAME_FIELDS = ("room_type_name", "ota_room_type_name", "mapped_room_type_name")
_ROOM_NAME_KEYWORDS = (
    "大床", "双床", "单床", "家庭床", "上下铺", "榻榻米", "圆床", "套房",
    "商务", "亲子", "情侣", "电竞", "棋牌", "观景", "景观", "影院", "光影",
    "浴缸", "零压", "智能", "投影", "阳台", "落地窗",
)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "").replace("¥", "").rstrip("%").strip())
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _field(label: str, value: Any, note: str = "") -> dict[str, Any]:
    return {"label": label, "value": value, "note": note}


def _item(no: int, score: float | None, status: str, source: str, fields: list[dict[str, Any]], note: str) -> dict[str, Any]:
    return {
        "standard_item_id": no,
        "participates_in_score": True,
        "item_score": score,
        "data_status": status,
        "source": source,
        "fields": fields,
        "fields_complete": True,
        "note": note,
    }


def _ctrip_yoy_item(result: dict[str, Any]) -> dict[str, Any] | None:
    visual = result.get("visual_diagnosis") or {}
    base = next(
        (
            row for row in visual.get("items") or []
            if isinstance(row, dict) and int(row.get("standard_item_id") or 0) == 1
        ),
        None,
    )
    if not base:
        return None
    item = copy.deepcopy(base)
    revenue_yoy = None
    for record in item.get("records") or []:
        if not isinstance(record, dict) or _text(record.get("metric_name")) != "房费":
            continue
        revenue_yoy = _number(record.get("yoy"))
        break
    if revenue_yoy is None:
        for field in item.get("fields") or []:
            if isinstance(field, dict) and _text(field.get("label")) in {"本月YOY", "月度YOY"}:
                revenue_yoy = _number(field.get("value"))
                if revenue_yoy is not None and abs(revenue_yoy) > 1:
                    revenue_yoy /= 100
                break
    if revenue_yoy is None:
        return item
    score = 10.0 if revenue_yoy >= 0.20 else 8.0 if revenue_yoy >= 0 else 6.0 if revenue_yoy >= -0.20 else 0.0
    item["item_score"] = score
    item["score_ratio"] = score / 10
    item["data_status"] = "success"
    return item


def _has_yoyo_activity(sections: dict[str, Any]) -> bool:
    return any(
        _text(row.get("activity_name")) in _CTRIP_YOYO_ACTIVITY_NAMES
        for row in sections.get("ctrip_promotion_activity") or []
        if isinstance(row, dict)
    )


def _yoyo_campaign_orders(sections: dict[str, Any]) -> float | None:
    for row in sections.get("ctrip_promotion_activity_performance") or []:
        if not isinstance(row, dict) or _text(row.get("campaign_name")) != _CTRIP_YOYO_PROMOTION_CAMPAIGN:
            continue
        orders = _number(row.get("campaign_quantity"))
        if orders is not None:
            return orders
    return None


def _scan_item(sections: dict[str, Any]) -> dict[str, Any]:
    source = "携程 eBooking / YOYO卡或扫码住"
    if not _has_yoyo_activity(sections):
        return _item(
            7,
            0.0,
            "success",
            source,
            [_field("参与状态", "未参与"), _field("近30天扫码订单", 0), _field("日均扫码订单", 0)],
            "未参与YOYO卡&扫码住专享促销或专享红包，本项按未参与计0分。",
        )
    orders = _yoyo_campaign_orders(sections)
    if orders is None:
        return _item(
            7,
            None,
            "missing",
            source,
            [_field("参与状态", "已参与")],
            "已参与YOYO卡/扫码住活动，等待近30天活动订单数据。",
        )
    daily = orders / 30
    score = 5.0 if orders > 120 else 2.5 if orders >= 60 else 0.0
    return _item(
        7,
        score,
        "success",
        source,
        [
            _field("参与状态", "已参与"),
            _field("近30天扫码订单", orders),
            _field("日均扫码订单", round(daily, 2)),
        ],
        "近30天少于60单得0分，60至120单得2.5分，超过120单得5分。",
    )


def _patch_promotion(item: dict[str, Any] | None) -> None:
    if not isinstance(item, dict):
        return
    spend = next(
        (
            _number(field.get("value")) for field in item.get("fields") or []
            if isinstance(field, dict) and _text(field.get("label")) == "推广投入"
        ),
        None,
    )
    if spend is not None and spend < 1000:
        item["item_score"] = 0.0
        item["data_status"] = "success"
        item["note"] = "近30天推广投入低于1000元，本项直接得0分，无需等待ROI。"


def _room_name(row: dict[str, Any]) -> str:
    for key in _ROOM_NAME_FIELDS:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _room_name_item(sections: dict[str, Any]) -> dict[str, Any]:
    source = "ctrip_ota_goods_price_mapping"
    rows = [dict(row) for row in sections.get("ctrip_goods_price_mapping") or [] if isinstance(row, dict)]
    if not rows:
        return _item(11, None, "missing", source, [], "等待携程售卖房型快照。")
    rooms: dict[str, dict[str, Any]] = {}
    missing_names = 0
    for index, row in enumerate(rows):
        name = _room_name(row)
        if not name:
            missing_names += 1
            continue
        room_id = _text(row.get("ota_room_type_id") or row.get("room_type_id"))
        key = room_id or re.sub(r"\s+", "", name)
        rooms.setdefault(key, {"name": name, "room_type_id": room_id})
    if not rooms or missing_names:
        return _item(
            11,
            None,
            "partial",
            source,
            [_field("售卖商品数", len(rows)), _field("可识别售卖房型数", len(rooms))],
            "部分商品缺少房型名称，不能使用冗长商品名称代替房型名称计分。",
        )
    records = []
    for room in rooms.values():
        name = room["name"]
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", name))
        hits = [keyword for keyword in _ROOM_NAME_KEYWORDS if keyword in chinese]
        qualified = len(chinese) > 5 and bool(hits)
        records.append({**room, "length": len(chinese), "qualified": qualified, "reason": f"包含{hits[0]}信息" if hits else "未识别床型、场景、卖点或人群信息"})
    qualified_count = sum(1 for row in records if row["qualified"])
    ratio = qualified_count / len(records)
    score = 4.0 if ratio >= 0.8 else 2.4 if ratio >= 0.5 else 0.0
    item = _item(
        11,
        score,
        "success",
        source,
        [
            _field("售卖商品数", len(rows)),
            _field("售卖房型数", len(records)),
            _field("合格房型", qualified_count),
            _field("合格房型占比", f"{ratio:.1%}"),
        ],
        "按携程售卖房型名称去重评分；合格占比不低于80%得4分，50%至80%得2.4分，低于50%得0分。",
    )
    item["records"] = records
    return item


def _flash_item(sections: dict[str, Any]) -> dict[str, Any]:
    source = "携程 eBooking / 闪住服务入口"
    row = next(
        (
            dict(candidate)
            for candidate in sections.get("ctrip_promotion_status") or []
            if isinstance(candidate, dict)
            and _text(candidate.get("activity_code")).lower() == _FLASH_STAY_CODE
            and _text(candidate.get("activity_name")) == _FLASH_STAY_NAME
        ),
        None,
    )
    if not row:
        return _item(17, None, "missing", source, [], "等待闪住开通状态数据，可人工补充。")
    status = _text(row.get("status")).lower()
    if status not in {"joined", "not_joined"}:
        return _item(17, None, "pending_rule", source, [_field("参与状态", "待核验")], "闪住参与状态无法确认，可人工补充。")
    joined = status == "joined"
    return _item(
        17,
        2.0 if joined else 0.0,
        "success",
        source,
        [_field("参与状态", "已参与" if joined else "未参与")],
        "闪住已参与得2分，未参与得0分。",
    )


def _video_count(row: dict[str, Any] | None) -> str:
    if not row:
        return "暂无数据"
    uploaded = _number(row.get("uploaded_count"))
    required = _number(row.get("required_count"))
    if uploaded is None:
        return "暂无数据"
    uploaded_text = str(int(uploaded)) if uploaded.is_integer() else str(uploaded)
    if required is None:
        return uploaded_text
    required_text = str(int(required)) if required.is_integer() else str(required)
    return f"{uploaded_text}/{required_text}"


def _homepage_video_item(sections: dict[str, Any]) -> dict[str, Any]:
    source = "携程视频上传状态"
    rows = [dict(row) for row in sections.get("ctrip_video_upload_status") or [] if isinstance(row, dict)]
    by_type = {_text(row.get("video_type")): row for row in rows}
    if "hotel_listing_video" not in by_type and "hotel_list_video" in by_type:
        by_type["hotel_listing_video"] = by_type["hotel_list_video"]
    detail = by_type.get("hotel_detail_video")
    fields = [
        _field(label, _video_count(by_type.get(video_type)), "")
        for video_type, label in _CTRIP_VIDEO_TYPES
    ]
    detail_count = _number(detail.get("uploaded_count")) if detail else None
    if detail_count is None:
        return _item(20, None, "missing", source, fields, "等待详情页视频上传状态数据。")
    return _item(
        20,
        1.0 if detail_count > 0 else 0.0,
        "success",
        source,
        fields,
        "详情页视频上传数量大于0得1分，等于0得0分；列表页和房型视频仅展示。",
    )


def _listing_content(sections: dict[str, Any]) -> tuple[dict[str, str], bool, bool]:
    rows = [dict(row) for row in sections.get("ctrip_promotion_status") or [] if isinstance(row, dict)]
    by_code = {_text(row.get("activity_code")).lower(): row for row in rows}
    content: dict[str, str] = {}
    configured = True
    found = False
    for code, label in _LISTING_CONTENT_CODES:
        row = by_code.get(code)
        if row:
            found = True
        detail = _text(row.get("status_detail")) if row else ""
        if not row or _text(row.get("status")).upper() != "CONFIGURED" or not detail:
            configured = False
            continue
        content[label] = detail
    return content, configured, found


def _patch_page_entry(item: dict[str, Any] | None, sections: dict[str, Any]) -> None:
    if not isinstance(item, dict):
        return
    content, configured, found = _listing_content(sections)
    content_text = "；".join(f"{label}：{value}" for label, value in content.items())
    fields = [dict(field) for field in item.get("fields") or [] if isinstance(field, dict)]
    replacement = _field(
        "列表页推荐词 / 标签 / 卖点",
        content_text if content_text else "未配置" if found else "待接入",
        "已读取列表页推荐词和短标签配置" if configured else "推荐词和短标签需均已配置且有内容才得分",
    )
    for index, field in enumerate(fields):
        if _text(field.get("label")) == replacement["label"]:
            fields[index] = replacement
            break
    else:
        fields.append(replacement)
    item["fields"] = fields
    item["listing_content"] = content
    base_score = _number(item.get("item_score"))
    if base_score is not None:
        item["item_score"] = min(3.0, base_score + (1.0 if configured else 0.0))
    item["data_status"] = "success" if configured else "partial"
    item["source"] = "携程酒店名称与列表页展示状态"
    item["note"] = (
        "门店后缀、热门商圈词和列表页推荐词/短标签均已取得。"
        if configured
        else "列表页推荐词和短标签未完整配置，不能取得该项1分。"
    )


def _mark_partial_reputation(item: dict[str, Any] | None) -> None:
    if not isinstance(item, dict):
        return
    platforms = [row for row in item.get("platforms") or [] if isinstance(row, dict)]
    missing = [str(row.get("platform_name") or "") for row in platforms if row.get("data_status") != "success"]
    if missing and len(missing) < len(platforms):
        item["data_status"] = "partial"
        item["note"] = f"当前仅按已取得的平台评分；缺少{'、'.join(missing)}数据，携程口碑总项仍不完整。"


def align_ctrip_scores(result: dict[str, Any], sections: dict[str, Any]) -> None:
    items = result.setdefault("ctrip_items", {})
    yoy_item = _ctrip_yoy_item(result)
    if yoy_item:
        items["1"] = yoy_item
    visual = result.get("visual_diagnosis") or {}
    room_item = next(
        (
            row for row in visual.get("items") or []
            if isinstance(row, dict) and int(row.get("standard_item_id") or 0) == 2
        ),
        None,
    )
    if room_item:
        items["2"] = copy.deepcopy(room_item)
    items["7"] = _scan_item(sections)
    _patch_promotion(items.get("9") or items.get(9))
    _patch_page_entry(items.get("10") or items.get(10), sections)
    items["11"] = _room_name_item(sections)
    _mark_partial_reputation(items.get("12") or items.get(12))
    items["17"] = _flash_item(sections)
    items["20"] = _homepage_video_item(sections)


__all__ = ["align_ctrip_scores"]
