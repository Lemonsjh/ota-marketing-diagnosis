from marketing_diagnosis.dual_channel_report import (
    CTRIP_CONTENT_CLEANUP_SCRIPT,
    _strip_hidden_source_details,
)
from marketing_diagnosis.reporting_current import build_ctrip_html


def test_known_ctrip_source_blocks_are_removed_from_generated_html():
    source = """
    <div class='ctrip-source-v55'><b>携程数据来源：</b>携程 eBooking</div>
    <div class='ctrip-competition-source'><b>数据口径：</b>近30天</div>
    <div class='psi-source-v53'>
      <div><b>页面数据来源</b>携程 eBooking</div>
      <div><b>数据库来源与计分口径</b>ctrip_ota_psi_score</div>
    </div>
    """

    output = _strip_hidden_source_details(source)

    assert "携程数据来源" not in output
    assert "数据口径" not in output
    assert "页面数据来源" not in output
    assert "数据库来源与计分口径" not in output


def test_runtime_cleanup_covers_summary_source_column_and_key_conclusion():
    assert "数据来源" in CTRIP_CONTENT_CLEANUP_SCRIPT
    assert "重点结论" in CTRIP_CONTENT_CLEANUP_SCRIPT
    assert "removeSummarySourceColumn" in CTRIP_CONTENT_CLEANUP_SCRIPT
    assert ".page[data-channel-view=\"ctrip\"]" in CTRIP_CONTENT_CLEANUP_SCRIPT


def test_standalone_ctrip_report_uses_customer_facing_cleanup():
    document = build_ctrip_html({})

    assert "<select class='scope-select'" not in document
    assert "导出报告" in document
    assert "<div class='ctrip-source-v55'>" not in document
    assert "未接入字段统一显示“待接入”" not in document
    assert "<div class='page' data-channel-view='ctrip'>" in document
    assert "id='CTRIP_VISIBLE_EXPLANATION_CLEANUP_SCRIPT'" in document
