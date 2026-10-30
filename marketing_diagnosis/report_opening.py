"""Unscored, cross-platform facts displayed before the diagnosis sections."""
from __future__ import annotations

import html
import re


LABELS = {"meituan": "美团", "ctrip": "携程"}
STYLE = """<style id='REPORT_OPENING_STYLE'>
.report-opening{display:grid;gap:20px;margin:20px 0}
.report-opening .diagnosis-card{margin:0;min-width:0}
.report-opening .opening-metrics{grid-template-columns:repeat(3,minmax(0,1fr));margin-bottom:18px}
.report-opening .opening-metrics strong.is-missing{font-size:18px}
.report-opening .opening-table{overflow-x:auto}
.report-opening table{width:100%;min-width:0;table-layout:auto;white-space:nowrap}
.report-opening th,.report-opening td{text-align:right;padding:10px 9px}
.report-opening th:first-child,.report-opening td:first-child{text-align:left}
.report-opening .opening-note{margin:14px 0 0;color:var(--muted);font-size:12px;line-height:1.7}
.opening-order-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.opening-order-group{min-width:0}.opening-order-group h4{margin:0 0 12px;font-size:15px;color:var(--green)}
@media(max-width:600px){.opening-order-groups{grid-template-columns:minmax(0,1fr)}.report-opening .opening-metrics{grid-template-columns:1fr}}
@media print{.report-opening article{break-inside:avoid}}
</style>"""


def _text(value):
    return html.escape(str(value), quote=True)


def _num(value):
    return "—" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


def _pct(value):
    return "—" if value is None else f"{value:.2%}"


def _metric(label, value, unavailable=False):
    missing = " class='is-missing'" if unavailable else ""
    return f"<div class='reputation-metric-v32'><small>{_text(label)}</small><strong{missing}>{_text(value)}</strong></div>"


def _table(headers, rows):
    return ("<div class='table-scroll opening-table'><table class='output-table'><thead><tr>"
            + "".join(f"<th scope='col'>{_text(value)}</th>" for value in headers)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{_text(value)}</td>" for value in row) + "</tr>" for row in rows)
            + "</tbody></table></div>")


def opening_html(payload):
    reviews, orders = payload["reviews"], payload["orders"]
    total = reviews["total"]
    review_rows = [(LABELS[row["platform"]], _num(row["checkout_orders"]),
                    _num(row["review_count"]), _pct(row["rate"])) for row in reviews["platforms"]]
    review = ("<article class='diagnosis-card'><div class='card-top'><div class='card-title'><h3>昨日点评率</h3>"
              f"<p>{_text(payload['checkout_date'])} 退房 · {_text(payload['review_date'])} 新增评论</p></div></div>"
              "<div class='result-area'><div class='reputation-grid-v32 opening-metrics'>"
              + _metric("合计点评率", _pct(total["rate"]) if total["rate"] is not None else "暂不可计算", total["rate"] is None)
              + _metric("昨日退房订单", _num(total["checkout_orders"]))
              + _metric("今日新增评论", _num(total["review_count"])) + "</div>"
              + _table(["平台", "昨日退房订单", "今日新增评论", "点评率"], review_rows)
              + "<p class='opening-note'>点评率＝今日新增评论数÷昨日退房订单数；今日评论截至报告生成时。美团含大众点评，携程含去哪儿。</p></div></article>")
    groups = []
    for label, points, aggregate in [("合计", orders["daily_totals"], True),
                                    *[(LABELS[row["platform"]], row["daily_points"], False) for row in orders["platforms"]]]:
        rows = []
        by_date = {point["business_date"]: point for point in points}
        for total_point in orders["daily_totals"]:
            day = total_point["business_date"]
            point = by_date.get(day, {})
            row = [day[5:]] if aggregate else []
            row += [_num(point.get("own_orders")), _num(point.get("market_orders")), _pct(point.get("share"))]
            rows.append(row)
        headers = (["日期"] if aggregate else []) + ["本店订单", "竞争圈订单", "本店占比"]
        groups.append(f"<div class='opening-order-group'><h4>{_text(label)}</h4>"
                      + (_table(headers, rows) if rows else "<p>暂无数据</p>") + "</div>")
    order = (f"<article class='diagnosis-card'><div class='card-top'><div class='card-title'><h3>近7天订单与商圈占比</h3><p>{_text(payload['order_period_start'])} 至 {_text(payload['order_period_end'])} · 每日全日订单</p></div></div>"
             "<div class='result-area'><div class='opening-order-groups'>" + "".join(groups) + "</div>"
             "<p class='opening-note'>竞争圈订单为商家数×同行均值的估算值；合计按当日有数据的平台求和，再计算本店占比。</p></div></article>")
    return "<section class='report-opening' aria-label='经营数据概览'>" + review + order + "</section>"


def patch_opening_html(document, result):
    payload = result.get("report_opening")
    if not payload or "class='report-opening'" in document:
        return document
    content = opening_html(payload)
    # Each channel view retains the same aggregate facts between its overview
    # and diagnosis summary, inside the report's existing main column.
    document, count = re.subn(r"<(?:details|section)\b[^>]*\bid=(['\"])(?:ctrip-)?summary\1[^>]*>",
                             lambda m: content + m[0], document)
    if not count:
        document = re.sub(r"<article\b[^>]*\bid=(['\"])(?:ctrip-)?rule-1\1[^>]*>",
                          lambda m: content + m[0], document)
    return document.replace("</head>", STYLE + "</head>", 1)


def opening_markdown(result):
    payload = result.get("report_opening")
    if not payload:
        return ""
    reviews, orders = payload["reviews"], payload["orders"]
    total = reviews["total"]
    lines = ["## 昨日点评率", f"{payload['checkout_date']}退房／{payload['review_date']}新增评论",
             f"合计：退房{_num(total['checkout_orders'])}单，新增评论{_num(total['review_count'])}条，点评率{_pct(total['rate'])}。"]
    lines.extend(f"- {LABELS[row['platform']]}：退房{_num(row['checkout_orders'])}单，新增评论{_num(row['review_count'])}条，点评率{_pct(row['rate'])}。" for row in reviews["platforms"])
    lines += ["", f"## 近7天订单与商圈占比（{payload['order_period_start']}至{payload['order_period_end']}）"]
    for label, points in [("合计", orders["daily_totals"]), *[(LABELS[r["platform"]], r["daily_points"]) for r in orders["platforms"]]]:
        lines.append(f"### {label}")
        for row in points:
            lines.append(f"- {row['business_date']}：本店{_num(row['own_orders'])}单，竞争圈估算{_num(row['market_orders'])}单，占比{_pct(row['share'])}。")
    return "\n".join(lines) + "\n\n"
