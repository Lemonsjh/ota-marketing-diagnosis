import base64
import re
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch

from openpyxl import load_workbook

from marketing_diagnosis.latest import normalize_dataset, process
from marketing_diagnosis.metrics_core import promotion_metrics
from marketing_diagnosis.rectification import _template, build_plan, write_rectification
from marketing_diagnosis.rectification_balances import load_promotion_balances
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
    assert rows["C9"]["allow_manual_current"] is True
    assert rows["C23"]["status"] == "待补资料" and rows["C23"]["facts"] == []
    assert rows["C23"]["goal"] == "完成10条问答"
    assert rows["C23"]["review"] == "每天5条"


def test_meituan_daily_maintenance_matches_the_excel_template():
    plan = build_plan(result())
    rows = {row["id"]: row for row in plan["rows"]}
    assert "M15" not in rows
    assert rows["M25"]["title"] == "动销单维护"
    assert rows["M25"]["stage"] == rows["M20"]["stage"] == "持续执行 每日维护"
    assert rows["M25"]["goal"] == rows["C28"]["goal"] == "根据酒店当日出租率情况进行调整"
    assert rows["M25"]["status"] == rows["C28"]["status"] == "待业务确认"
    assert rows["M25"]["allow_manual_current"] is True
    assert rows["C28"]["allow_manual_current"] is True
    assert rows["M16"]["excel_row"] == 15 and rows["M25"]["excel_row"] == 19
    book = load_workbook(BytesIO(base64.b64decode(_template(plan))))
    for row in rows.values():
        assert book[row["channel"]].cell(row["excel_row"], 2).value == row["title"]
    assert "A4:A18 A19:A24" in str(book["美团"].merged_cells)
    for sheet, metadata_cell in ((book["携程"], "A36"), (book["美团"], "A28")):
        assert {"F1:I1", "F2:I2"} <= {str(cell_range) for cell_range in sheet.merged_cells.ranges}
        assert sheet["F1"].value == "启动日：________　运营负责人：________"
        assert sheet["F2"].value == "酒店负责人：________　日期双方确认"
        assert sheet[metadata_cell].value == f"诊断周期 {plan['period']}　报告版本 {plan['key'][1]}"


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
    assert rows["M16"]["facts"] == []
    assert "PSI 可取消率（不含具体截止时间） 100%" in rows["C11"]["facts"]
    assert "商品名称标注（以具体退改条款为准） 入住当天18:00前免费取消" in rows["M13"]["facts"]
    assert "商品快照房型 双床房" in rows["M14"]["facts"]
    assert rows["M4"]["facts"] == []


def test_promotion_balances_read_only_the_enabled_account_for_this_hotel():
    cursor = Mock()
    captured = datetime(2026, 11, 24, 9)
    cursor.fetchall.return_value = [{"total_balance": Decimal("0.00"), "currency": "CNY", "snapshot_time": captured}]
    balances = load_promotion_balances(cursor, "zhiting", ["meituan"])
    assert balances == {"meituan": {"total_balance": "0.00", "currency": "CNY", "snapshot_time": str(captured)}}
    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args.args
    assert all(field in sql for field in ("hotel_id = %s", "platform_scope = %s", "promotion_type = %s",
                                          "snapshot_time <= %s", "ORDER BY snapshot_time DESC LIMIT 1"))
    assert params[:3] == ("zhiting", "meituan", "promotion_tong")
    cursor.execute.side_effect = RuntimeError("optional source unavailable")
    assert load_promotion_balances(cursor, "zhiting", ["ctrip"]) == {}
    assert cursor.execute.call_args.args[1][:3] == ("zhiting", "ctrip", "pyramid")


def test_promotion_balances_add_unscored_facts_to_the_correct_plan_rows():
    payload = result()
    payload["visual_diagnosis"]["items"].append({
        "standard_item_id": 9, "data_status": "success",
        "fields": [{"label": "近30天推广投入", "value": 500}],
    })
    balances = {
        "meituan": {"total_balance": "0.00", "snapshot_time": "2026-11-24 09:00:00"},
        "ctrip": {"total_balance": "101.25", "snapshot_time": "2026-11-24 10:00:00"},
    }
    data = normalize_dataset({"promotion_balances": balances})
    with patch("marketing_diagnosis.hotel_profiles.channels", return_value={"meituan", "ctrip"}), \
         patch("marketing_diagnosis.latest._process", return_value=payload):
        payload = process(data)
    rows = {row["id"]: row for row in build_plan(payload)["rows"]}
    assert rows["M22"]["facts"][:2] == ["推广通账户余额 ¥0.00", "近30天推广投入 500"]
    assert rows["C32"]["facts"] == ["金字塔账户余额 ¥101.25"]
    assert rows["C32"]["status"] == "已带入部分现状"
    assert "balance_missing" not in rows["M22"] and "balance_missing" not in rows["C32"]
    payload["promotion_balances"]["ctrip"]["total_balance"] = None
    del payload["promotion_balances"]["meituan"]
    rows = {row["id"]: row for row in build_plan(payload)["rows"]}
    assert rows["M22"]["balance_missing"] == "推广通账户余额 无"
    assert rows["M22"]["facts"][0] == "近30天推广投入 500"
    assert rows["C32"]["balance_missing"] == "金字塔账户余额 无"
    assert rows["C32"]["status"] == "待补资料" and rows["C32"]["facts"] == []


def test_meituan_rectification_lists_only_registration_activities():
    payload = result()
    rows = [
        {"platform": "meituan", "activity_source_type": "报名活动", "activity_name": "平台报名一",
         "snapshot_time": "2026-11-24 09:02:02"},
        {"platform": "meituan", "activity_source_type": "自助促销", "activity_name": "门店自设"},
        {"platform": "ctrip", "activity_source_type": "报名活动", "activity_name": "携程活动"},
    ]
    payload["metrics"] = {"promotion": promotion_metrics(rows, [{"platform": "meituan"}])}
    plan_rows = {row["id"]: row for row in build_plan(payload)["rows"]}
    assert plan_rows["M16"]["facts"] == ["报名活动 1 项", "平台报名一", "数据日期 2026-11-24"]
    assert "活动快照记录数 1" in plan_rows["C15"]["facts"]


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
