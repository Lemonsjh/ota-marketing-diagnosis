"""Unscored, cross-platform facts displayed before the diagnosis sections."""
from __future__ import annotations

import html
import math
import re


LABELS = {"meituan": "美团", "ctrip": "携程"}
STYLE = """<style id='REPORT_OPENING_STYLE'>
.report-opening{display:grid;gap:24px;margin:20px 0;color:#13243b;font-size:16px;container-type:inline-size}
.report-opening .diagnosis-card{margin:0;min-width:0}
.report-opening .card-top{padding:30px 36px 14px;border-bottom:0}
.report-opening .card-title h3{font-size:clamp(26px,2.3cqw,34px);line-height:1.4;font-weight:750}
.report-opening .card-title p{font-size:16px;line-height:1.6;margin-top:8px;color:#66788a}
.report-opening .result-area{padding:20px 36px 28px}
.opening-review{display:grid;grid-template-columns:1.05fr .95fr repeat(var(--opening-platforms),1.05fr);align-items:end;gap:28px;padding:6px 0 10px}
.opening-review>div+div{border-left:1px solid #e1e8ec;padding-left:28px}
.opening-rate strong{display:block;color:#008563;font-size:clamp(48px,6cqw,80px);line-height:1.2;letter-spacing:-2px;font-variant-numeric:tabular-nums}
.opening-rate small{display:block;margin-top:8px;font-size:16px;color:#637589}
.opening-review strong.is-missing{font-size:26px;letter-spacing:0}
.opening-counts,.opening-platform-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.opening-counts strong{display:block;font-size:clamp(32px,3.4cqw,48px);line-height:1.3;font-variant-numeric:tabular-nums}
.opening-counts small,.opening-platform-facts small{display:block;margin-top:7px;font-size:16px;color:#637589;white-space:nowrap}
.opening-platform h4{margin:0 0 18px;font-size:18px;color:#008563}
.opening-platform-facts{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.opening-platform-facts strong{font-size:24px;line-height:1.4;font-variant-numeric:tabular-nums;white-space:nowrap}
.opening-order-panel{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:34px;align-items:start}
.opening-order-toolbar{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:34px;align-items:center;margin-bottom:14px}.opening-order-toolbar h4{margin:0;font-size:20px}
.report-opening [hidden]{display:none!important}
.opening-chart{min-width:0;padding-top:12px}.opening-chart h4{margin:0 0 18px;font-size:18px;font-weight:650}
.opening-chart-scroll{overflow-x:auto}.opening-chart svg{display:block;width:100%;min-width:500px;height:auto}
.opening-chart svg text{font-family:inherit;font-size:19px;fill:#637589}
.opening-chart circle{cursor:help;stroke:#fff;stroke-width:2;transition:r .15s ease}
.opening-chart circle:hover,.opening-chart circle:focus{r:8;outline:none}
.opening-detail{min-width:0}.opening-tabs{display:flex;gap:8px;border-bottom:1px solid #dbe4e9}
.opening-tabs button{flex:1;border:0;border-bottom:3px solid transparent;background:transparent;color:#637589;font:inherit;font-size:17px;font-weight:650;padding:12px 8px;cursor:pointer}
.opening-tabs button[aria-selected=true]{color:#008563;border-bottom-color:#008563}
.opening-tabs button:focus-visible{outline:2px solid #008563;outline-offset:-3px}
.report-opening .opening-table{overflow-x:auto}
.report-opening table{width:100%;min-width:0;table-layout:fixed;white-space:nowrap;font-size:18px}
.report-opening .opening-table th,.report-opening .opening-table td{width:auto;min-width:0;max-width:none;text-align:right;padding:12px 10px;font-size:18px;line-height:1.5}
.report-opening .opening-table th{font-size:15px;font-weight:600;background:#f5f8fa;color:#566779}
.report-opening th:first-child,.report-opening td:first-child{text-align:left}
.report-opening .opening-note{margin:20px 0 0;color:#637589;font-size:14px;line-height:1.7}
@media(max-width:1250px){.opening-review{grid-template-columns:1fr 1fr}.opening-review>div:nth-child(3){border-left:0;padding-left:0}.opening-order-panel,.opening-order-toolbar{grid-template-columns:1fr}.opening-order-toolbar{gap:14px}}
@container(max-width:1000px){.opening-review{grid-template-columns:1fr 1fr}.opening-review>div:nth-child(3){border-left:0;padding-left:0}}
@media(max-width:600px){.report-opening .card-top{padding:22px 18px 8px}.report-opening .result-area{padding:16px 18px 22px}.report-opening .card-title h3{font-size:22px}.opening-review{gap:24px 18px}.opening-review>div+div{padding-left:18px}.opening-rate strong{font-size:38px;letter-spacing:-1px}.opening-counts strong{font-size:28px}.opening-platform{grid-column:1/-1}.opening-review>div.opening-platform{border-left:0;padding:18px 0 0;border-top:1px solid #e1e8ec}.opening-platform h4{margin-bottom:12px}.opening-chart svg{min-width:500px}.opening-order-panel{gap:16px}.report-opening table{min-width:340px}}
@media(max-width:600px){.opening-counts{grid-template-columns:1fr;gap:14px}.opening-counts small{font-size:14px;white-space:normal}}
@media print{.report-opening article{break-inside:avoid}.opening-order-panel{grid-template-columns:1fr 1fr}.opening-chart svg{min-width:0}}
</style>"""

SCRIPT = """<script id='REPORT_OPENING_SCRIPT'>
(function(){
 function setup(){document.querySelectorAll('.report-opening').forEach(function(root){
  const tabs=Array.from(root.querySelectorAll('[data-opening-tab]'));
  function select(tab,focus){
   tabs.forEach(function(button){const active=button===tab;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;});
   root.querySelectorAll('[data-opening-panel]').forEach(function(panel){panel.hidden=panel.dataset.openingPanel!==tab.dataset.openingTab;});
   root.querySelector('[data-opening-title]').textContent=tab.textContent+'本店占比趋势';
   if(focus)tab.focus();
  }
  tabs.forEach(function(tab,index){
   tab.addEventListener('click',function(){select(tab,false);});
   tab.addEventListener('keydown',function(event){
    let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;
    event.preventDefault();select(tabs[next],true);
   });
  });
 });}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();</script>"""


def _text(value):
    return html.escape(str(value), quote=True)


def _num(value):
    return "—" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


def _pct(value):
    return "—" if value is None else f"{value:.2%}"


def _metric(label, value, unavailable=False):
    missing = " class='is-missing'" if unavailable else ""
    return f"<div><strong{missing}>{_text(value)}</strong><small>{_text(label)}</small></div>"


def _table(headers, rows):
    return ("<div class='table-scroll opening-table'><table class='output-table'><thead><tr>"
            + "".join(f"<th scope='col'>{_text(value)}</th>" for value in headers)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{_text(value)}</td>" for value in row) + "</tr>" for row in rows)
            + "</tbody></table></div>")


def _chart(points, label, chart_id):
    if not points:
        return "<p>暂无数据</p>"
    shares = [point["share"] for point in points if point.get("share") is not None]
    ceiling = max(.02, math.ceil(max(shares, default=0) * 1.25 / .02) * .02)
    left, right, top, bottom = 76, 724, 50, 366
    parts = [f"<svg viewBox='0 0 760 424' role='img' aria-label='{_text(label)}本店占比趋势，缺失日期不连线'>",
             f"<defs><linearGradient id='{chart_id}' x1='0' y1='0' x2='0' y2='1'><stop offset='0%' stop-color='#00976d' stop-opacity='.18'/><stop offset='100%' stop-color='#00976d' stop-opacity='.02'/></linearGradient></defs>"]
    for tick in range(4):
        y = bottom - (bottom - top) * tick / 3
        parts.append(f"<line x1='{left}' x2='{right}' y1='{y:.1f}' y2='{y:.1f}' stroke='#e7edf1'/><text x='{left-14}' y='{y+6:.1f}' text-anchor='end'>{ceiling*tick/3:.2%}</text>")
    segments, segment, dots = [], [], []
    for index, point in enumerate(points):
        x = left + (right - left) * index / max(len(points) - 1, 1)
        day, share = point["business_date"], point.get("share")
        parts.append(f"<line x1='{x:.1f}' x2='{x:.1f}' y1='{top}' y2='{bottom}' stroke='#f0f3f5'/><text x='{x:.1f}' y='410' text-anchor='middle'>{_text(day[5:])}</text>")
        if share is None:
            if segment:
                segments.append(segment)
                segment = []
            continue
        y = bottom - (bottom - top) * share / ceiling
        segment.append((x, y))
        anchor = "start" if index == 0 else "end" if index == len(points)-1 else "middle"
        dots.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='6' fill='#008563' tabindex='0'><title>{_text(day)} · {_text(label)}：{_pct(share)}</title></circle><text x='{x:.1f}' y='{y-18:.1f}' text-anchor='{anchor}' style='fill:#163a31;font-weight:600'>{_pct(share)}</text>")
    if segment:
        segments.append(segment)
    for segment in segments:
        coordinates = " ".join(f"{x:.1f},{y:.1f}" for x, y in segment)
        parts.append(f"<polygon points='{segment[0][0]:.1f},{bottom} {coordinates} {segment[-1][0]:.1f},{bottom}' fill='url(#{chart_id})'/><polyline points='{coordinates}' fill='none' stroke='#008563' stroke-width='3'/>")
    return "".join(parts + dots) + "</svg>"


def opening_html(payload, prefix="opening"):
    reviews, orders = payload["reviews"], payload["orders"]
    total = reviews["total"]
    platform_facts = "".join(
        f"<div class='opening-platform'><h4>{LABELS[row['platform']]}</h4><div class='opening-platform-facts'>"
        + _metric("退房订单", _num(row["checkout_orders"]))
        + _metric("新增评论", _num(row["review_count"]))
        + _metric("点评率", _pct(row["rate"])) + "</div></div>" for row in reviews["platforms"])
    review = ("<article class='diagnosis-card'><div class='card-top'><div class='card-title'><h3>昨日点评率</h3>"
              f"<p>{_text(payload['checkout_date'])} 退房 · {_text(payload['review_date'])} 新增评论</p></div></div>"
              f"<div class='result-area'><div class='opening-review' style='--opening-platforms:{len(reviews['platforms'])}'>"
              "<div class='opening-rate' title='点评率＝今日新增评论数÷昨日退房订单数；美团含大众点评，携程含去哪儿。'>"
              + _metric("合计点评率", _pct(total["rate"]) if total["rate"] is not None else "暂不可计算", total["rate"] is None) + "</div><div class='opening-counts'>"
              + _metric("昨日退房订单", _num(total["checkout_orders"]))
              + _metric("今日新增评论", _num(total["review_count"])) + "</div>" + platform_facts + "</div></div></article>")
    panels = []
    series = [("total", "合计", orders["daily_totals"]),
              *[(row["platform"], LABELS[row["platform"]], row["daily_points"]) for row in orders["platforms"]]]
    for key, label, points in series:
        rows = []
        by_date = {point["business_date"]: point for point in points}
        aligned = []
        for total_point in orders["daily_totals"]:
            day = total_point["business_date"]
            point = by_date.get(day, {})
            aligned.append({"business_date": day, "share": point.get("share")})
            row = [day[5:]]
            row += [_num(point.get("own_orders")), _num(point.get("market_orders")), _pct(point.get("share"))]
            rows.append(row)
        panels.append(f"<div class='opening-order-panel' data-opening-panel='{key}' id='{prefix}-{key}' role='tabpanel' aria-labelledby='{prefix}-{key}-tab'{' hidden' if key!='total' else ''}>"
                      "<div class='opening-chart'><div class='opening-chart-scroll'>"
                      + _chart(aligned, label, f"{prefix}-{key}-fill") + "</div></div>"
                      + "<div class='opening-detail'>"
                      + (_table(["日期", "本店订单", "竞争圈订单", "本店占比"], rows) if rows else "<p>暂无数据</p>") + "</div></div>")
    tabs = "".join(f"<button type='button' role='tab' id='{prefix}-{key}-tab' data-opening-tab='{key}' aria-controls='{prefix}-{key}' aria-selected='{str(key=='total').lower()}' tabindex='{0 if key=='total' else -1}'>{label}</button>" for key, label, _ in series)
    order = (f"<article class='diagnosis-card'><div class='card-top'><div class='card-title'><h3>近7天订单与商圈占比</h3><p>{_text(payload['order_period_start'])} 至 {_text(payload['order_period_end'])} · 每日全日订单</p></div></div>"
             "<div class='result-area'><div class='opening-order-toolbar'><h4 data-opening-title>合计本店占比趋势</h4><div class='opening-tabs' role='tablist' aria-label='订单平台'>" + tabs + "</div></div>" + "".join(panels)
             + "<p class='opening-note'>竞争圈订单为商家数×同行均值的估算值；合计按当日有数据的平台求和，再计算本店占比。</p></div></article>")
    return "<section class='report-opening' aria-label='经营数据概览'>" + review + order + "</section>"


def patch_opening_html(document, result):
    payload = result.get("report_opening")
    if not payload or "class='report-opening'" in document:
        return document
    # Each channel view retains the same aggregate facts between its overview
    # and diagnosis summary, inside the report's existing main column.
    document, count = re.subn(r"<(?:details|section)\b[^>]*\bid=(['\"])(?:ctrip-)?summary\1[^>]*>",
                             lambda m: opening_html(payload, "ctrip-opening" if "ctrip-summary" in m[0] else "meituan-opening") + m[0], document)
    if not count:
        document = re.sub(r"<article\b[^>]*\bid=(['\"])(?:ctrip-)?rule-1\1[^>]*>",
                          lambda m: opening_html(payload, "ctrip-opening" if "ctrip-rule" in m[0] else "meituan-opening") + m[0], document)
    return document.replace("</head>", STYLE + "</head>", 1).replace("</body>", SCRIPT + "</body>", 1)


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
