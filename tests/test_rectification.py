import base64
import re
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook

from marketing_diagnosis.latest import normalize_dataset, process
from marketing_diagnosis.rectification import _template, build_plan, write_rectification
from marketing_diagnosis.reporting_current import write_reports


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
    assert rows["C23"]["status"] == "待补资料" and rows["C23"]["facts"] == []
    assert rows["C23"]["goal"] == "完成10条问答"


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


def test_rectification_reuses_platform_snapshots_with_their_actual_meaning():
    payload = result()
    payload["metrics"] = {
        "price_ladder": {"data_period": {"end": "2026-11-24"}, "by_platform": {
            "ctrip": {"min_price": 0, "max_price": 265, "product_count": 5},
            "meituan": {"min_price": 50, "max_price": 260},
        }},
        "promotion": {"by_platform": {"ctrip": {"activity_count": 6}, "meituan": {"activity_count": 11}}},
        "room_types": {"items": [
            {"platform": "meituan", "room_type_name": "双床房", "product_count": 1,
             "product_names": ["双床房-入住当天18:00前免费取消"]},
            {"platform": "ctrip", "room_type_name": "携程大床", "product_count": 1},
        ]},
    }
    payload["ctrip_items"]["6"] = {"metrics": [
        {"metric_code": "cancellation_rate", "metric_value": 100, "connected": True},
    ]}
    rows = {row["id"]: row for row in build_plan(payload)["rows"]}
    assert "最低商品挂牌价（元） 0" in rows["C8"]["facts"]
    assert "活动快照记录数 11" in rows["M16"]["facts"]
    assert "PSI 可取消率（不含具体截止时间） 100%" in rows["C11"]["facts"]
    assert "商品名称标注（以具体退改条款为准） 入住当天18:00前免费取消" in rows["M13"]["facts"]
    assert "商品快照房型 双床房" in rows["M14"]["facts"]
    assert rows["M4"]["facts"] == []


def test_template_goals_and_concise_statuses_are_kept_separate():
    payload = result()
    payload["visual_diagnosis"]["items"].extend([
        {"standard_item_id": 18, "data_status": "zero", "fields": [
            {"label": "开通状态", "value": "CLOSED"}, {"label": "生效状态", "value": "未生效"},
        ]},
        {"standard_item_id": 21, "data_status": "zero", "fields": [
            {"label": "酒店官方视频", "value": "1/1"}, {"label": "酒店官方预览视频", "value": "0/1"},
            {"label": "房型视频", "value": "9/9"},
        ]},
    ])
    payload["ctrip_items"]["20"] = {"data_status": "success", "fields": [
        {"label": "详情页视频", "value": "1/1"}, {"label": "列表页视频", "value": "0/1"},
    ]}
    rows = {row["id"]: row for row in build_plan(payload)["rows"]}
    assert all(row["goal"] for row in rows.values())
    assert rows["M5"]["facts"] == ["未开通"] and rows["M5"]["goal"] == "大床房和双床房"
    assert rows["M10"]["facts"] == ["无首页预览视频"]
    assert rows["C20"]["facts"] == ["无列表页视频"]
    assert rows["M4"]["facts"] == []


def test_plan_is_a_separate_page_with_a_report_link(tmp_path):
    payload = {**process(normalize_dataset({})), "hotel_id": "zhiting", "run_id": "test"}
    paths = write_reports(payload, tmp_path)
    report = (tmp_path / "report.html").read_text(encoding="utf-8")
    plan = (tmp_path / "rectification.html").read_text(encoding="utf-8")
    assert paths["rectification_html"] == str(tmp_path / "rectification.html")
    assert "href='rectification.html'" in report and "rectification-data" not in report
    assert 'href="report.html"' in plan and "id='rectification-data'" in plan
    book = load_workbook(BytesIO(base64.b64decode(_template(build_plan(payload)))))
    assert re.findall(r'<th scope="col"[^>]*>([^<]+)</th>', plan) == [cell.value for cell in book.active[3]]
    assert "下载 Excel" in plan


def test_plan_failure_does_not_break_report(tmp_path):
    payload = {**process(normalize_dataset({})), "hotel_id": "zhiting", "run_id": "test"}
    with patch("marketing_diagnosis.rectification._template", side_effect=OSError):
        paths = write_reports(payload, tmp_path)
    assert "rectification_html" not in paths
    assert "rectification-open" not in (tmp_path / "report.html").read_text(encoding="utf-8")
    assert not (tmp_path / "rectification.html").exists()
