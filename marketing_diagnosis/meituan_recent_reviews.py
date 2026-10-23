"""Meituan reputation: daily review counts and a 15-day trend chart."""
from __future__ import annotations

import datetime as dt
import html
import math
import re
from typing import Any
from zoneinfo import ZoneInfo

SECTION = "meituan_review_daily_counts"
DIAGNOSTIC = "meituan_review_trend_15d"
_CARD = re.compile(r"<article\b[^>]*\bid=['\"]rule-13['\"][^>]*>.*?</article>", re.S)
SERIES = (("total", "合计", "#087f64"),)
STYLE = """<style id='MEITUAN_REVIEW_TREND_STYLE'>
#meituan-review-trend{padding:24px 20px;border-top:1px solid #e1e9e5}
#meituan-review-trend h4{margin:0 0 8px;font-size:17px;color:#173e32}
#meituan-review-trend p{margin:0 0 14px;color:#687b72;font-size:12px}
#meituan-review-trend .review-legend{display:flex;gap:20px;flex-wrap:wrap;margin:16px 0;font-size:13px}
#meituan-review-trend .review-legend i{display:inline-block;width:18px;height:3px;vertical-align:middle;margin-right:6px;background:var(--line)}
#meituan-review-trend .review-plot{overflow-x:auto;border:1px solid #e4ebe7;border-radius:12px;background:#fbfdfc}
#meituan-review-trend svg{display:block;width:100%;min-width:720px;height:auto}
#meituan-review-trend svg text{font-family:inherit;fill:#64786e;font-size:12px}
#meituan-review-trend circle{cursor:help;stroke:#fff;stroke-width:1.5}
#meituan-review-trend circle:focus{outline:2px solid #174e3d}
#meituan-review-trend .review-note{margin-top:12px}
</style>"""


def _window() -> tuple[dt.date, dt.date]:
    end = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    return end - dt.timedelta(days=14), end


def load_recent_reviews(cursor, table: str, hotel_id: str | None):
    """Read only grouped counts; no reviewer names or review content."""
    from marketing_diagnosis.db_loader import _safe_identifier, _table_columns

    start, end = _window()
    diagnostic = {
        "table": table, "status": "empty", "rows": 0,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "period_days": 15, "includes_today": True,
    }
    columns, error = _table_columns(cursor, table)
    if error or not {"hotel_id", "channel_source", "review_time"}.issubset(columns) or not hotel_id:
        return [], {**diagnostic, "status": "error" if error else "schema_drift"}
    try:
        cursor.execute(
            "SELECT DATE(review_time) AS review_date, channel_source, COUNT(*) AS review_count "
            f"FROM {_safe_identifier(table)} "
            "WHERE hotel_id=%s AND review_time>=%s AND review_time<%s "
            "GROUP BY DATE(review_time), channel_source ORDER BY review_date, channel_source",
            (hotel_id, start.isoformat(), (end + dt.timedelta(days=1)).isoformat()),
        )
        rows = [{**row, "hotel_id": hotel_id} for row in cursor.fetchall()]
    except Exception as exc:
        return [], {**diagnostic, "status": "error", "error_type": type(exc).__name__}
    return rows, {
        **diagnostic, "status": "ok", "rows": sum(int(row["review_count"]) for row in rows),
        "grouped_rows": len(rows), "hotel_filter_applied": True,
    }


def _item(result: dict[str, Any]) -> dict[str, Any] | None:
    return next((row for row in (result.get("visual_diagnosis") or {}).get("items", [])
                 if int(row.get("standard_item_id") or 0) == 13), None)


def _remove_yesterday(item: dict[str, Any]) -> None:
    item["fields"] = [field for field in item.get("fields", [])
                      if field.get("label") != "昨日新增点评数"]
    for key in ("yesterday_review_date", "yesterday_new_review_count", "recent_reviews"):
        item.pop(key, None)
    item["note"] = re.sub(r"昨日新增点评数[^。]*(?:。|$)", "", item.get("note") or "").strip()


def _channel(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "大众点评" in text or "dianping" in text:
        return "dianping"
    if "美团" in text or "meituan" in text:
        return "meituan"
    return "other"


def attach_recent_reviews(result: dict[str, Any], data: dict[str, Any]) -> None:
    item = _item(result)
    if item is None:
        return
    _remove_yesterday(item)
    start, end = _window()
    diagnostic = next((source.get("tables", {}).get(DIAGNOSTIC)
                       for source in data.get("source_diagnostics", [])
                       if source.get("tables", {}).get(DIAGNOSTIC)), {})
    start_day = diagnostic.get("period_start") or start.isoformat()
    end_day = diagnostic.get("period_end") or end.isoformat()
    points = {}
    if diagnostic.get("status") == "ok":
        first = dt.date.fromisoformat(start_day)
        for offset in range(15):
            day = (first + dt.timedelta(days=offset)).isoformat()
            points[day] = {"review_date": day, "total": 0, "meituan": 0, "dianping": 0, "other": 0}
        for row in (data.get("sections") or {}).get(SECTION, []):
            if not data.get("hotel_id") or str(row.get("hotel_id")) != str(data["hotel_id"]):
                continue
            point = points.get(str(row.get("review_date") or "")[:10])
            if point is not None:
                count = int(row.get("review_count") or 0)
                point[_channel(row.get("channel_source"))] += count
                point["total"] += count
    item["review_trend"] = {
        "period_start": start_day, "period_end": end_day, "period_days": 15,
        "includes_today": True, "data_status": diagnostic.get("status") or "not_integrated",
        "daily_points": list(points.values()),
    }


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _plot(points: list[dict[str, Any]]) -> str:
    top, bottom, left, right = 32, 248, 52, 888
    step = max(1, math.ceil(max(point["total"] for point in points) / 4))
    maximum = step * 4
    x = lambda index: left + (right - left) * index / (len(points) - 1)
    y = lambda value: bottom - (bottom - top) * value / maximum
    parts = ["<svg viewBox='0 0 920 300' role='img' aria-labelledby='review-trend-title review-trend-desc'>",
             "<title id='review-trend-title'>近15天每日新增评论数</title>",
             "<desc id='review-trend-desc'>按评论发布时间逐日统计各渠道新增评论合计；悬停或聚焦数据点查看日期和条数。</desc>",
             f"<rect x='{x(14)-22:.1f}' y='{top}' width='44' height='{bottom-top}' fill='#edf5ef'/>"]
    for tick in range(5):
        value = tick * step
        parts.append(f"<line x1='{left}' y1='{y(value):.1f}' x2='{right}' y2='{y(value):.1f}' stroke='#e2ebe5'/>")
        parts.append(f"<text x='{left-12}' y='{y(value)+4:.1f}' text-anchor='end'>{value}</text>")
    for index, point in enumerate(points):
        label = point["review_date"][5:]
        parts.append(f"<text x='{x(index):.1f}' y='274' text-anchor='middle'>{_e(label)}</text>")
    for key, label, color in SERIES:
        coordinates = " ".join(f"{x(i):.1f},{y(point[key]):.1f}" for i, point in enumerate(points))
        parts.append(f"<polyline points='{coordinates}' fill='none' stroke='{color}' stroke-width='3'/>")
        for index, point in enumerate(points):
            tip = _e(f"{point['review_date']} · {label}：{point[key]}条")
            parts.append(f"<circle cx='{x(index):.1f}' cy='{y(point[key]):.1f}' r='4' fill='{color}' tabindex='0' aria-label='{tip}'><title>{tip}</title></circle>")
    return "".join(parts) + "</svg>"


def _chart(payload: dict[str, Any]) -> str:
    points = payload.get("daily_points") or []
    heading = ("<section id='meituan-review-trend'><h4>近15天每日新增评论趋势</h4>"
               f"<p>{_e(payload['period_start'])} 至 {_e(payload['period_end'])}（含当日） · 按评论发布时间统计</p>")
    if not points:
        return heading + "<p>评论趋势暂未取得，请检查数据来源。</p></section>"
    legend = "".join(f"<span><i style='--line:{color}'></i>{label} {_e(sum(p[key] for p in points))}条</span>"
                     for key, label, color in SERIES)
    return (heading + f"<div class='review-legend'>{legend}</div><div class='review-plot'>"
            + _plot(points) + "</div><p class='review-note'>纵轴：新增评论数（条）；横轴：评论日期。"
            "无评论日期显示0；右侧浅色区域为当日，当日尚未结束，数据截至报告生成时。"
            "悬停或聚焦数据点可查看具体条数；本图不参与口碑评分。</p></section>")


def patch_recent_reviews_html(document: str, result: dict[str, Any]) -> str:
    from marketing_diagnosis.reporting_v32 import _reputation_card

    item = _item(result)
    if item is None:
        return document
    _remove_yesterday(item)
    payload = item.get("review_trend")
    if not payload:
        return document
    # Remove the superseded detail table, pagination assets and earlier chart style.
    document = re.sub(r"<section id='(?:meituan-recent-reviews|meituan-review-trend)'[^>]*>.*?</section>", "", document, flags=re.S)
    document = re.sub(r"<style id='(?:MEITUAN_RECENT_REVIEWS_STYLE|MEITUAN_REVIEW_TREND_STYLE)'>.*?</style>", "", document, flags=re.S)
    document = re.sub(r"<script id='MEITUAN_RECENT_REVIEWS_SCRIPT'>.*?</script>", "", document, flags=re.S)
    card = _reputation_card(item)
    card = card.replace("展示美团与大众点评评分、点评数、未回复数，以及按点评时间统计的昨日新增点评数。",
                        "展示美团与大众点评评分、点评数、未回复数及近15天每日新增评论趋势。")
    card = re.sub(r"(<div class='title-meta-item title-period'><small>统计周期</small><strong>).*?(</strong>)",
                  r"\g<1>评分最新快照 / 评论近15天\2", card, count=1)
    card = card.replace("</article>", _chart(payload) + "</article>")
    document, count = _CARD.subn(lambda _: card, document, count=1)
    return document.replace("</head>", STYLE + "</head>", 1) if count else document
