from datetime import datetime, timedelta
from unittest.mock import patch
import re

import pytest

from marketing_diagnosis.latest import normalize_dataset, process
from marketing_diagnosis.meituan_market_share import METRIC_CODE, SECTION, TITLE, patch_market_share
from marketing_diagnosis.reporting_current import build_html, build_ctrip_html, build_meituan_html, write_reports

NOW = datetime(2026, 10, 15, 16)


def row(day="2026-10-14", **values):
    return {"hotel_id": "audit", "business_date": day, "metric_code": METRIC_CODE,
            "snapshot_time": "2026-10-15 10:00:00", "metric_value": 20,
            "peer_average": 8.05, "competitor_rank": "2/21", "metric_unit": "间夜", **values}


def report(rows):
    with patch("marketing_diagnosis.meituan_market_share.report_time", return_value=NOW):
        data = normalize_dataset({SECTION: rows})
        data.update(hotel_id="audit", hotel_name="测试酒店")
        result = process(data)
    return {**result, "hotel_id": "audit", "hotel_name": "测试酒店",
            "period_start": "2026-09-16", "period_end": "2026-10-15"}


def item(result):
    return next(i for i in result["visual_diagnosis"]["items"] if i["standard_item_id"] == 3)


def test_yesterday_share_and_exact_seven_days_survive_real_pipeline():
    result = report([row()])
    market = item(result)["market_share"]
    assert market["yesterday"]["market_room_nights"] == 181
    assert market["yesterday"]["share"] == pytest.approx(20 / 181)
    assert [p["business_date"] for p in market["daily_points"]] == [f"2026-10-{d:02}" for d in range(8, 15)]
    assert item(result)["item_score"] is None
    assert item(result)["item_name"] == TITLE


def test_missing_yesterday_does_not_borrow_latest_available_day():
    market = item(report([row(day="2026-10-13")]))["market_share"]
    assert market["yesterday"]["share"] is None
    assert market["daily_points"][-2]["share"] == pytest.approx(20 / 181)


def test_written_html_and_markdown_both_use_new_item(tmp_path):
    from pathlib import Path

    paths = write_reports(report([row()]), tmp_path)
    assert "过去7天份额趋势" in Path(paths["report_html"]).read_text(encoding="utf-8")
    markdown = Path(paths["report_markdown"]).read_text(encoding="utf-8")
    assert TITLE in markdown and "11.05%" in markdown
    assert "2026-10-08：—" in markdown


@pytest.mark.parametrize("updates", [
    {"snapshot_time": "2026-10-14 20:00:00"},
    {"snapshot_time": "2026-10-15 17:00:00"},
    {"hotel_id": "another-hotel"}, {"metric_code": "PAY_ORDER_CNT"},
    {"metric_value": None}, {"peer_average": None}, {"peer_average": "nan"},
    {"metric_value": -1}, {"competitor_rank": "2"}, {"competitor_rank": "2/0"},
    {"competitor_rank": "22/21"}, {"metric_unit": "order"},
])
def test_unusable_values_never_generate_a_share(updates):
    assert item(report([row(**updates)]))["market_share"]["yesterday"]["share"] is None


def test_true_zero_is_zero_share_not_missing():
    point = item(report([row(metric_value=0)]))["market_share"]["yesterday"]
    assert point["share"] == 0
    assert point["market_room_nights"] == 161


def test_zero_market_is_not_a_zero_percent_share():
    point = item(report([row(metric_value=0, peer_average=0)]))["market_share"]["yesterday"]
    assert point["share"] is None and point["reason"] == "zero_market"


def test_latest_snapshot_wins_and_out_of_window_dates_are_excluded():
    result = report([row(metric_value=5, snapshot_time="2026-10-15 09:00:00"), row(),
                     row(day="2026-10-07"), row(day="2026-10-15")])
    assert len(item(result)["records"]) == 1
    assert item(result)["market_share"]["yesterday"]["own_room_nights"] == 20


def test_each_days_competition_count_is_used():
    result = report([row(), row(day="2026-10-13", competitor_rank="2/11")])
    points = item(result)["market_share"]["daily_points"]
    assert points[-2]["share"] == pytest.approx(20 / (20 + 8.05 * 10))


def test_html_card_chart_summary_and_channel_isolation():
    rows = [row(day=f"2026-10-{d:02}", metric_value=10 + d) for d in range(8, 15)]
    result = report(rows)
    document = build_html(result)
    card = re.search(r"<article[^>]*id='rule-3'[\s\S]*?</article>", document)[0]
    assert TITLE in card and "过去7天份额趋势" in card
    assert "<svg" in card and card.count("<circle ") == 7
    assert "广告曝光" not in card and "评分规则待确认" in card
    assert f"<span>03</span>{TITLE}" in document
    assert "data-title='曝光数据分析'" not in document
    assert "MEITUAN_MARKET_SHARE_STYLE" not in build_ctrip_html(result)
    assert TITLE in build_meituan_html(result)


def test_svg_breaks_at_missing_dates_and_missing_yesterday_shows_pending():
    result = report([row(day="2026-10-08"), row(day="2026-10-10")])
    document = build_meituan_html(result)
    card = re.search(r"<article[^>]*id='rule-3'[\s\S]*?</article>", document)[0]
    assert card.count("<circle ") == 2
    assert "stroke-width='3'" not in card
    assert "<strong>待更新</strong>" in card


def test_unknown_mixed_hotel_scope_fails_closed():
    result = report([])
    patch_market_share(result, {SECTION: [row(), row(hotel_id="other")]}, as_of=NOW)
    assert item(result)["market_share"]["yesterday"]["share"] is None


def test_database_query_is_exact_and_does_not_use_report_period():
    from marketing_diagnosis.meituan_market_data import fetch_market_rows
    required = {"hotel_id", "business_date", "snapshot_time", "metric_code",
                "metric_value", "peer_average", "competitor_rank"}
    with patch("marketing_diagnosis.db_loader._table_columns", return_value=(required, None)), \
         patch("marketing_diagnosis.db_loader._fetch", return_value=([row()], {})) as fetch, \
         patch("marketing_diagnosis.meituan_market_data.report_time", return_value=NOW):
        rows, _ = fetch_market_rows(None, "meituan_ota_business_metrics", "audit")
    assert rows == [row()]
    assert fetch.call_args.args[4] == ["audit", METRIC_CODE, "2026-10-08", "2026-10-15", str(NOW)]


def test_database_missing_hotel_column_is_not_queried_unscoped():
    from marketing_diagnosis.meituan_market_data import fetch_market_rows
    with patch("marketing_diagnosis.db_loader._table_columns", return_value=({"business_date"}, None)), \
         patch("marketing_diagnosis.db_loader._fetch") as fetch:
        rows, diag = fetch_market_rows(None, "metrics", "audit")
    assert not rows and diag["status"] == "error"
    fetch.assert_not_called()
