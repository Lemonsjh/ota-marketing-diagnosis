"""Server-rendered share card and gap-preserving SVG; no external chart runtime."""
from __future__ import annotations

import html
import math
import re
from typing import Any

from marketing_diagnosis.meituan_exposure_monthly import _find_item, _ITEM03_RE
from marketing_diagnosis.meituan_market_share import DESCRIPTION, TITLE

STYLE = """<style id='MEITUAN_MARKET_SHARE_STYLE'>
.mshare{display:grid;gap:22px}.mshare-top{display:grid;grid-template-columns:1.1fr 2fr;gap:22px;align-items:center}
.mshare-hero{padding:20px 24px;background:#eef8f3;border:1px solid #cde5d9;border-radius:14px}
.mshare small{display:block;color:#657b73;font-size:13px}.mshare-hero strong{display:block;margin-top:8px;color:#117a54;font-size:46px;font-weight:800;line-height:1.2;font-variant-numeric:tabular-nums}
.mshare-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.mshare-facts strong{display:block;margin-top:10px;font-size:23px;color:#243c32;font-variant-numeric:tabular-nums}
.mshare-chart{border:1px solid #dfe9e3;border-radius:14px;padding:18px 20px;background:#fcfefd}.mshare-chart-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;margin-bottom:8px}.mshare-chart-head h4{margin:0;font-size:16px;color:#243c32}
.mshare-chart svg{display:block;width:100%;height:auto}.mshare-note{margin:0;color:#6c7a74;font-size:12px;line-height:1.7}.mshare details{font-size:13px}.mshare summary{cursor:pointer;color:#187b57}.mshare table{width:100%;border-collapse:collapse;margin-top:10px;white-space:nowrap}.mshare th,.mshare td{padding:10px;text-align:right;border-bottom:1px solid #e5ece7}.mshare th:first-child,.mshare td:first-child{text-align:left}
@media(max-width:700px){.mshare-top{grid-template-columns:1fr}.mshare-facts{gap:10px}.mshare-facts strong{font-size:19px}.mshare-hero strong{font-size:38px}.mshare-chart{padding:14px 8px}.mshare-chart-head{padding:0 8px;flex-wrap:wrap}}
</style>"""


def _num(value: Any) -> str:
    return "—" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


def _pct(value: Any) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"


def _chart(points: list[dict[str, Any]]) -> str:
    shares = [p["share"] for p in points if p.get("share") is not None]
    ceiling = min(1, max(.05, math.ceil(max(shares, default=0) * 1.15 / .05) * .05))
    left, right, top, bottom = 88, 744, 42, 230
    parts = ["<svg viewBox='0 0 800 280' role='img' aria-label='过去7天每日入住间夜份额；缺失日期断开，不按零展示'>"]
    for i in range(5):
        y, value = bottom - (bottom - top) * i / 4, ceiling * i / 4
        parts.append(f"<line x1='{left}' x2='{right}' y1='{y}' y2='{y}' stroke='#e3ebe6'/><text x='53' y='{y + 4}' text-anchor='end' fill='#718279' font-size='12'>{value * 100:g}%</text>")
    previous = None
    for index, point in enumerate(points):
        x, share = left + index * (right - left) / 6, point.get("share")
        day = html.escape(point["business_date"])
        parts.append(f"<text x='{x}' y='262' text-anchor='middle' fill='#61796c' font-size='13'>{day[5:]}</text>")
        if share is None:
            previous = None
            parts.append(f"<text x='{x}' y='{bottom - 12}' text-anchor='middle' fill='#98a79f' font-size='12'>缺失</text>")
            continue
        y = bottom - (bottom - top) * share / ceiling
        if previous:
            parts.append(f"<line x1='{previous[0]}' y1='{previous[1]}' x2='{x}' y2='{y}' stroke='#16845b' stroke-width='3'/>")
        label_x = x + 4 if index == 0 else x - 4 if index == len(points) - 1 else x
        anchor = "start" if index == 0 else "end" if index == len(points) - 1 else "middle"
        parts.append(f"<circle cx='{x}' cy='{y}' r='5' fill='#16845b' stroke='white' stroke-width='2'><title>{day}：{_pct(share)}</title></circle><text x='{label_x}' y='{y - 13}' text-anchor='{anchor}' fill='#13734f' font-size='13' font-weight='700'>{_pct(share)}</text>")
        previous = x, y
    parts.append("</svg>")
    return "".join(parts)


def _content(item: dict[str, Any]) -> str:
    market = item["market_share"]
    yesterday, points = market["yesterday"], market["daily_points"]
    day = html.escape(yesterday["business_date"])
    share = _pct(yesterday["share"]) if yesterday["share"] is not None else "待更新"
    rank = f"{yesterday['rank']}/{yesterday['hotel_count']}" if yesterday["rank"] else "—"
    rows = "".join(f"<tr><td>{html.escape(p['business_date'])}</td><td>{_num(p['own_room_nights'])}</td><td>{_num(p['market_room_nights'])}</td><td>{_pct(p['share'])}</td></tr>" for p in points)
    missing = sum(p["share"] is None for p in points)
    return (f"<div class='mshare'><div class='mshare-top'><div class='mshare-hero'><small>昨日本店大盘份额 · {day}</small><strong>{share}</strong></div>"
            f"<div class='mshare-facts'><div><small>本店入住间夜</small><strong>{_num(yesterday['own_room_nights'])}</strong></div><div><small>大盘入住间夜（估算）</small><strong>{_num(yesterday['market_room_nights'])}</strong></div><div><small>本店排名 / 竞争圈酒店数</small><strong>{rank}</strong></div></div></div>"
            f"<div class='mshare-chart'><div class='mshare-chart-head'><h4>过去7天份额趋势</h4><small>{points[0]['business_date']} 至 {day}</small></div>{_chart(points)}"
            f"<p class='mshare-note'>{f'有 {missing} 天数据待补充，缺失日期留空、不连线。' if missing else '每日独立计算，展示完整日终数据。'}</p></div>"
            "<p class='mshare-note'>份额＝本店入住间夜÷［本店入住间夜＋同行平均入住间夜×（竞争圈酒店数－1）］。大盘与份额为估算值，不等同于全店出租率或订单份额。昨日数据未到齐时不使用其他日期替代。</p>"
            f"<details><summary>查看每日数据</summary><div style='overflow-x:auto'><table><thead><tr><th>营业日期</th><th>本店间夜</th><th>大盘间夜（估算）</th><th>本店份额</th></tr></thead><tbody>{rows}</tbody></table></div></details></div>")


def patch_market_html(document: str, result: dict[str, Any]) -> str:
    item = _find_item((result.get("visual_diagnosis") or {}).get("items"), 3)
    if not item or "market_share" not in item or not _ITEM03_RE.search(document):
        return document
    day = item["market_share"]["yesterday"]["business_date"]
    def replace(match):
        head = re.sub(r"data-title=(['\"])[^'\"]*\1", f"data-title='{TITLE}'", match[1])
        top = (f"<div class='card-top'><div class='rule-no'>03</div><div class='card-title'><h3>{TITLE}</h3><p>{DESCRIPTION}</p></div>"
               f"<div class='card-tags'><div class='title-meta-item title-period'><small>统计周期</small><strong>昨日 · {day[5:]}</strong></div>"
               "<div class='title-meta-item title-score pending'><small>当前得分</small><div class='title-score-value'><strong>待确认</strong><span>评分规则待确认</span></div></div></div></div>")
        return head + top + "<div class='result-area'>" + _content(item) + "</div>" + match[3]
    document = _ITEM03_RE.sub(replace, document, count=1)
    document = document.replace("曝光数据分析", TITLE)
    document = document.replace("展示截至昨日的近30天总曝光、非广告曝光、广告曝光及广告曝光占比。", DESCRIPTION)
    document = document.replace("展示整体曝光、非广告曝光、广告曝光及每日广告曝光占比。", DESCRIPTION)
    return document.replace("</head>", STYLE + "</head>", 1) if "MEITUAN_MARKET_SHARE_STYLE" not in document else document
