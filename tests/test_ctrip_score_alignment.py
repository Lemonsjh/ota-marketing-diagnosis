from __future__ import annotations

from marketing_diagnosis.channel_score_totals import ctrip_direct_total, meituan_direct_total
from marketing_diagnosis.ctrip_flow_rules import process


def _visual_item(no: int, score: float, **values):
    return {
        "standard_item_id": no,
        "item_score": score,
        "participates_in_score": True,
        **values,
    }


def test_ctrip_yoy_20_percent_gets_full_score_without_changing_meituan(monkeypatch):
    visual = {
        "items": [
            _visual_item(1, 8, records=[{"metric_name": "房费", "yoy": 0.20}]),
            _visual_item(2, 4.8),
        ]
    }

    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": visual, "ctrip_items": {}})
    result = process({"sections": {}})

    assert result["ctrip_items"]["1"]["item_score"] == 10
    assert meituan_direct_total(result) == 12.8
    assert ctrip_direct_total(result) == 14.8


def test_ctrip_scan_uses_five_point_boundaries(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {}})
    scores = []
    for orders in (59, 60, 120, 121):
        result = process(
            {
                "sections": {
                    "ctrip_promotion_activity": [{"activity_name": "YOYO卡&扫码住专享促销"}],
                    "ctrip_promotion_activity_performance": [
                        {"campaign_name": "YOYO卡&扫码住专享促销", "campaign_quantity": orders}
                    ],
                }
            }
        )
        scores.append(result["ctrip_items"]["7"]["item_score"])
    assert scores == [0, 2.5, 2.5, 5]


def test_ctrip_scan_without_the_named_activity_is_zero(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {}})
    result = process({"sections": {"ctrip_promotion_activity": [{"activity_name": "早订优惠"}]}})

    item = result["ctrip_items"]["7"]
    assert item["item_score"] == 0
    assert item["data_status"] == "success"
    assert item["fields"][0] == {"label": "参与状态", "value": "未参与", "note": ""}


def test_ctrip_scan_participation_without_campaign_orders_waits_for_data(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {}})
    result = process({"sections": {"ctrip_promotion_activity": [{"activity_name": "YOYO卡&扫码住专享红包"}]}})

    item = result["ctrip_items"]["7"]
    assert item["item_score"] is None
    assert item["data_status"] == "missing"


def test_ctrip_low_spend_is_zero_even_without_roi(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    base = {
        "standard_item_id": 9,
        "item_score": None,
        "data_status": "pending_rule",
        "participates_in_score": True,
        "fields": [{"label": "推广投入", "value": "¥999.00"}, {"label": "ROI", "value": None}],
    }
    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {"9": base}})
    result = process({"sections": {}})
    assert result["ctrip_items"]["9"]["item_score"] == 0
    assert result["ctrip_items"]["9"]["data_status"] == "success"


def test_ctrip_room_names_are_deduplicated_and_do_not_use_product_names(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {}})
    rows = [
        {"ota_room_type_id": "r1", "room_type_name": "舒适商务大床房", "ota_product_name": "很长的含早商品名称"},
        {"ota_room_type_id": "r1", "room_type_name": "舒适商务大床房", "ota_product_name": "很长的不含早商品名称"},
        {"ota_room_type_id": "r2", "room_type_name": "雅致特价大床房", "ota_product_name": "另一个很长商品名称"},
    ]
    result = process({"sections": {"ctrip_goods_price_mapping": rows}})
    item = result["ctrip_items"]["11"]
    assert item["item_score"] == 4
    assert item["fields"][1]["value"] == 2
    assert [row["name"] for row in item["records"]] == ["舒适商务大床房", "雅致特价大床房"]


def test_ctrip_flash_stay_is_a_scoring_item(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {}})
    joined = process({"sections": {"ctrip_promotion_status": [{"activity_code": "quick_check_inn", "activity_name": "闪住", "status": "joined"}]}})
    unjoined = process({"sections": {"ctrip_promotion_status": [{"activity_code": "quick_check_inn", "activity_name": "闪住", "status": "not_joined"}]}})
    assert joined["ctrip_items"]["17"]["item_score"] == 2
    assert joined["ctrip_items"]["17"]["fields"][0]["value"] == "已参与"
    assert unjoined["ctrip_items"]["17"]["item_score"] == 0
    assert unjoined["ctrip_items"]["17"]["fields"][0]["value"] == "未参与"


def test_ctrip_business_travel_not_joined_uses_enrollment_status(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {
        "16": {"standard_item_id": 16, "item_score": 1, "data_status": "success", "fields": []}
    }})
    result = process({"sections": {"ctrip_promotion_status": [{
        "activity_code": "business_travel_price", "status": "NOT_JOINED", "enabled": 0,
    }]}})

    item = result["ctrip_items"]["16"]
    assert item["item_score"] == 0
    assert item["fields"] == [
        {"label": "报名状态", "value": "未报名", "note": ""},
        {"label": "参与房型", "value": 0, "note": ""},
    ]


def test_ctrip_information_completeness_falls_back_to_psi_metric(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {
        "8": {"standard_item_id": 8, "item_score": None, "data_status": "pending_rule", "fields": []}
    }})
    result = process({"sections": {"ctrip_psi_metric": [
        {"metric_code": "information_completeness", "metric_value": 96, "snapshot_time": "2026-09-20 09:00:00"},
        {"metric_code": "information_completeness", "metric_value": 100, "snapshot_time": "2026-09-20 10:00:00"},
    ]}})

    item = result["ctrip_items"]["8"]
    assert item["item_score"] == 4
    assert item["fields"] == [
        {"label": "信息完整度", "value": "100%", "note": ""},
        {"label": "完整度结果", "value": "已达标", "note": ""},
    ]


def test_ctrip_information_completeness_keeps_primary_value(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {
        "8": {"standard_item_id": 8, "item_score": 0, "data_status": "success", "fields": [
            {"label": "信息完整度", "value": "96%", "note": ""}
        ]}
    }})
    result = process({"sections": {"ctrip_psi_metric": [
        {"metric_code": "information_completeness", "metric_value": 100},
    ]}})

    assert result["ctrip_items"]["8"]["fields"][0]["value"] == "96%"


def test_ctrip_homepage_video_scores_only_detail_page_upload(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {}})
    sections = {
        "ctrip_video_upload_status": [
            {"video_type": "hotel_detail_video", "uploaded_count": 0, "required_count": 1},
            {"video_type": "hotel_listing_video", "uploaded_count": 0, "required_count": 1},
            {"video_type": "room_type_video", "uploaded_count": 6, "required_count": 7},
        ]
    }
    item = process({"sections": sections})["ctrip_items"]["20"]

    assert item["item_score"] == 0
    assert [field["label"] for field in item["fields"]] == ["详情页视频", "列表页视频", "房型视频"]
    assert [field["value"] for field in item["fields"]] == ["0/1", "0/1", "6/7"]
    assert [field["note"] for field in item["fields"]] == [""] * 3


def test_ctrip_page_entry_uses_listing_recommendations_and_short_tags(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    base = {
        "standard_item_id": 10,
        "item_score": 2.0,
        "data_status": "partial",
        "fields": [{"label": "列表页推荐词 / 标签 / 卖点", "value": "待接入", "note": ""}],
    }
    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {"10": base}})
    result = process(
        {
            "sections": {
                "ctrip_promotion_status": [
                    {"activity_code": "listing_recommendation_words", "status": "CONFIGURED", "status_detail": "服务热情，设施齐全"},
                    {"activity_code": "listing_short_tags", "status": "CONFIGURED", "status_detail": "洗衣房，免费客房WiFi"},
                ]
            }
        }
    )
    item = result["ctrip_items"]["10"]

    assert item["item_score"] == 3
    assert item["data_status"] == "success"
    assert item["fields"][0]["value"] == "推荐词：服务热情，设施齐全；短标签：洗衣房，免费客房WiFi"
    assert item["listing_content"] == {"推荐词": "服务热情，设施齐全", "短标签": "洗衣房，免费客房WiFi"}


def test_ctrip_reputation_marks_missing_platforms_as_partial(monkeypatch):
    from marketing_diagnosis import ctrip_flow_rules

    reputation = {
        "standard_item_id": 12,
        "item_score": 5,
        "data_status": "success",
        "participates_in_score": True,
        "platforms": [
            {"platform_name": "携程", "data_status": "success"},
            {"platform_name": "去哪儿", "data_status": "missing"},
        ],
    }
    monkeypatch.setattr(ctrip_flow_rules, "upstream_process", lambda data: {"visual_diagnosis": {"items": []}, "ctrip_items": {"12": reputation}})
    result = process({"sections": {}})
    assert result["ctrip_items"]["12"]["data_status"] == "partial"
    assert "去哪儿" in result["ctrip_items"]["12"]["note"]
