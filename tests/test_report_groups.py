from marketing_diagnosis.report_groups import organize_report_html


def test_meituan_pair_is_grouped_with_its_chart_script_preserved():
    scan = "<article id='rule-7'><div class='rule-no'>07</div>扫码订单数据</article>"
    info = "<article id='rule-8'><div class='rule-no'>08</div><svg></svg>信息分数据</article>"
    more = "<article id='rule-10'><div class='rule-no'>10</div>页面展示</article>"
    chart_script = "<script>document.querySelector('#rule-8 svg');</script>"
    source = (
        "<head></head><nav class='side'></nav><main>"
        f"<div class='diagnosis-pair-v17'>{scan}{info}{chart_script}</div>{more}</main>"
    )

    report = organize_report_html(source, "meituan")

    assert info.replace(">08<", ">（一）<") in report.split("id='topic-3'", 1)[1].split("id='topic-4'", 1)[0]
    assert scan.replace(">07<", ">（一）<") in report.split("id='topic-7'", 1)[1].split("id='topic-8'", 1)[0]
    assert more.replace(">10<", ">（二）<") in report.split("id='topic-3'", 1)[1].split("id='topic-4'", 1)[0]
    assert report.count(chart_script) == 1
    assert "id='topic-original'" not in report
