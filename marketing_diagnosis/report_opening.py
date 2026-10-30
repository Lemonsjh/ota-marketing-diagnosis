"""Unscored, cross-platform facts displayed before the diagnosis sections."""
from __future__ import annotations

import html
import re


LABELS = {"meituan": "美团", "ctrip": "携程"}
STYLE = """<style id='REPORT_OPENING_STYLE'>
.report-opening{max-width:1440px;margin:22px auto 0;padding:0 24px;display:grid;gap:18px;box-sizing:border-box;color:var(--text,#213f35)}
.report-opening article{background:var(--panel,#fff);border:1px solid var(--line,#dfe7e4);border-radius:16px;overflow:hidden;min-width:0}
.report-opening header{padding:20px 22px 0}.report-opening h2{margin:0;font-size:19px;line-height:1.4}.report-opening p{margin:7px 0 0;font-size:12px;color:var(--muted,#718279)}
.report-opening .opening-metrics{display:flex;gap:24px;padding:20px 22px;flex-wrap:wrap}.opening-metrics>div{flex:1;min-width:80px}.opening-metrics small{display:block;font-size:12px;color:var(--muted,#718279)}.opening-metrics strong{display:block;margin-top:5px;color:var(--green,#16845b);font-size:27px;font-variant-numeric:tabular-nums;line-height:1.3}.opening-metrics strong.is-missing{font-size:16px}
.report-opening .opening-table{overflow-x:auto;padding:0 22px 20px}.report-opening table{width:100%;border-collapse:collapse;font-size:12px;white-space:nowrap}.report-opening th,.report-opening td{padding:10px 9px;border-bottom:1px solid var(--line,#dfe7e4);text-align:right}.report-opening th:first-child,.report-opening td:first-child{text-align:left;padding-left:0}.report-opening th{color:var(--muted,#718279);font-weight:500;background:transparent}.report-opening tbody tr:last-child td{border-bottom:0}.report-opening .opening-note{padding:0 22px 18px;margin:0;line-height:1.7}
.opening-order-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:0 14px;padding:18px 22px 0}.opening-order-group{min-width:0}.opening-order-group h3{margin:0 0 8px;font-size:14px;color:var(--green,#16845b)}.report-opening .opening-order-group .opening-table{padding:0 0 16px}
.report-opening table{min-width:0;table-layout:auto}
@media(max-width:1100px){.report-opening{grid-template-columns:1fr;padding:0 16px}}@media(max-width:600px){.opening-order-groups{grid-template-columns:minmax(0,1fr)}}@media print{.report-opening{display:block;margin-top:12px}.report-opening article{break-inside:avoid;margin-bottom:14px}}
</style>"""


def _text(value):
    return html.escape(str(value), quote=True)


def _num(value):
    return "—" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


def _pct(value):
    return "—" if value is None else f"{value:.2%}"


def _metric(label, value, unavailable=False):
    missing = " class='is-missing'" if unavailable else ""
    return f"<div><small>{_text(label)}</small><strong{missing}>{_text(value)}</strong></div>"


def _table(headers, rows):
    return ("<div class='opening-table'><table><thead><tr>"
            + "".join(f"<th scope='col'>{_text(value)}</th>" for value in headers)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{_text(value)}</td>" for value in row) + "</tr>" for row in rows)
            + "</tbody></table></div>")


def opening_html(payload):
    reviews, orders = payload["reviews"], payload["orders"]
    total = reviews["total"]
    review_rows = [(LABELS[row["platform"]], _num(row["checkout_orders"]),
                    _num(row["review_count"]), _pct(row["rate"])) for row in reviews["platforms"]]
    review = ("<article><header><h2>昨日点评率</h2>"
              f"<p>{_text(payload['checkout_date'])} 退房 · {_text(payload['review_date'])} 新增评论</p></header>"
              "<div class='opening-metrics'>"
              + _metric("合计点评率", _pct(total["rate"]) if total["rate"] is not None else "暂不可计算", total["rate"] is None)
              + _metric("昨日退房订单", _num(total["checkout_orders"]))
              + _metric("今日新增评论", _num(total["review_count"])) + "</div>"
              + _table(["平台", "昨日退房订单", "今日新增评论", "点评率"], review_rows)
              + "<p class='opening-note'>点评率＝今日新增评论数÷昨日退房订单数；今日评论截至报告生成时。美团含大众点评，携程含去哪儿。</p></article>")
    groups = []
    for label, points, aggregate in [("合计", orders["daily_totals"], True),
                                    *[(LABELS[row["platform"]], row["daily_points"], False) for row in orders["platforms"]]]:
        rows = []
        for point in points:
            row = [point["business_date"][5:], _num(point["own_orders"])]
            if not aggregate:
                row.append(f"{_num(point['merchant_count'])} × {_num(point['peer_average'])}")
            row += [_num(point["market_orders"]), _pct(point["share"])]
            rows.append(row)
        headers = ["日期", "本店订单"] + ([] if aggregate else ["商家数×均值"]) + ["竞争圈订单", "本店占比"]
        groups.append(f"<div class='opening-order-group'><h3>{_text(label)}</h3>"
                      + (_table(headers, rows) if rows else "<p>暂无数据</p>") + "</div>")
    order = (f"<article><header><h2>近7天订单与商圈占比</h2><p>{_text(payload['order_period_start'])} 至 {_text(payload['order_period_end'])} · 每日全日订单</p></header>"
             "<div class='opening-order-groups'>" + "".join(groups) + "</div>"
             "<p class='opening-note'>竞争圈订单为商家数×同行均值的估算值；合计按当日有数据的平台求和，再计算本店占比。</p></article>")
    return "<section class='report-opening' aria-label='经营数据概览'>" + review + order + "</section>"


def patch_opening_html(document, result):
    payload = result.get("report_opening")
    if not payload or "class='report-opening'" in document:
        return document
    content = opening_html(payload)
    # Keep the aggregate panel outside the channel tabs, so switching channels
    # leaves the same cross-platform totals visible and never duplicates them.
    document, count = re.subn(r"(</header>)(\s*<div\b[^>]*class=['\"][^'\"]*\bpage\b)",
                             lambda m: m[1] + content + m[2], document, count=1)
    if not count:
        document = re.sub(r"(<main\b[^>]*>)", lambda m: m[1] + content, document, count=1)
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
