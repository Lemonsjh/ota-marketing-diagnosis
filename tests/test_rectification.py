import base64
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook

from marketing_diagnosis.rectification import _template, build_plan, patch_rectification


def result():
    return {
        "hotel_id": "zhiting",
        "hotel_name": "智町",
        "run_id": "20261124-110000",
        "period_start": "2026-10-26",
        "period_end": "2026-11-24",
        "enabled_channels": ["ctrip", "meituan"],
        "visual_diagnosis": {"items": [
            {"standard_item_id": 13, "data_status": "zero", "item_score": 0, "fields": [
                {"label": "美团点评条数", "value": 0},
                {"label": "大众点评点评条数", "value": None},
            ]},
            {"standard_item_id": 7, "data_status": "success", "snapshot_time": "2026-09-01",
             "fields": [{"label": "月扫码订单", "value": 12}]},
            {"standard_item_id": 10, "data_status": "success", "fields": [
                {"label": "酒店展示名称", "value": "来源一"},
                {"label": "酒店展示名称", "value": "来源二"},
            ]},
        ]},
        "ctrip_items": {"12": {"platforms": [
            {"platform_key": "ctrip", "data_status": "success", "review_count": 11},
            {"platform_key": "qunar", "data_status": "success", "review_count": 99},
        ]}},
    }


def test_only_supported_facts_are_prefilled_and_statuses_are_distinct():
    plan = build_plan(result())
    rows = {row["id"]: row for row in plan["rows"]}
    assert len(rows) == 50
    assert rows["M23"]["facts"][0] == "美团点评条数 0"
    assert "大众点评" not in "\n".join(rows["M23"]["facts"])
    assert rows["C25"]["facts"][0] == "点评条数 11"
    assert rows["M21"]["status"] == "数据过期" and not rows["M21"]["facts"]
    assert rows["M9"]["status"] == "口径冲突" and not rows["M9"]["facts"]
    assert rows["M4"]["status"] == "待补资料"
    assert rows["C9"]["status"] == rows["C28"]["status"] == "待业务确认"
    assert rows["C23"]["status"] == "暂不实施"


def test_single_platform_workbook_keeps_layout_without_other_hotel_values():
    plan = build_plan({**result(), "enabled_channels": ["ctrip"]})
    assert len(plan["rows"]) == 29
    book = load_workbook(BytesIO(base64.b64decode(_template(plan))))
    assert book.sheetnames == ["携程"]
    sheet = book.active
    assert len(sheet[3]) == 9 and sheet["C4"].has_style and "A4:A22" in str(sheet.merged_cells)
    assert sheet["C4"].value is None and sheet["D4"].value is None
    assert "智町" in sheet["A2"].value
    assert all("泓斯佳" not in str(cell.value) and "空港" not in str(cell.value)
               for row in sheet for cell in row)


def test_plan_failure_does_not_break_report():
    report = "<head></head><body><header></header></body>"
    assert "rectification-open" in patch_rectification(report, result())
    with patch("marketing_diagnosis.rectification._template", side_effect=OSError):
        assert patch_rectification(report, result()) == report
