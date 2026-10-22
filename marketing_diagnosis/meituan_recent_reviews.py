"""Read and display the six approved review fields for the recent 15 days."""
from __future__ import annotations

import datetime as dt
import html
import re
from typing import Any
from zoneinfo import ZoneInfo

FIELDS = (
    "channel_source", "reviewer_name_masked", "review_score",
    "review_content", "review_time", "is_replied",
)
SECTION = "meituan_recent_reviews"
DIAGNOSTIC = "meituan_reviews_recent_15d"
_CARD = re.compile(r"<article\b[^>]*\bid=['\"]rule-13['\"][^>]*>.*?</article>", re.S)
_DETAIL = re.compile(r"<section id='meituan-recent-reviews'>.*?</section>", re.S)
STYLE = """<style id='MEITUAN_RECENT_REVIEWS_STYLE'>
#meituan-recent-reviews{padding:20px;border-top:1px solid #e1e9e5}
#meituan-recent-reviews h4{margin:0 0 8px;font-size:16px}
#meituan-recent-reviews p{margin:0 0 14px;color:#687b72;font-size:12px}
#meituan-recent-reviews .table-scroll{overflow-x:auto}
#meituan-recent-reviews table{width:100%;min-width:850px;border-collapse:collapse}
#meituan-recent-reviews th,#meituan-recent-reviews td{padding:12px;border-bottom:1px solid #e4ebe7;text-align:left;vertical-align:top}
#meituan-recent-reviews th{white-space:nowrap;background:#f5f9f7}
#meituan-recent-reviews td:nth-child(4){min-width:280px;max-width:650px;white-space:pre-wrap;overflow-wrap:anywhere}
#meituan-recent-reviews td:nth-child(5){min-width:145px;white-space:nowrap}
</style>"""


def _window() -> tuple[dt.date, dt.date]:
    end = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    return end - dt.timedelta(days=14), end


def load_recent_reviews(cursor, table: str, hotel_id: str | None):
    from marketing_diagnosis.db_loader import _safe_identifier, _table_columns

    start, end = _window()
    diagnostic = {
        "table": table, "status": "empty", "rows": 0,
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "period_days": 15, "includes_today": True,
    }
    columns, error = _table_columns(cursor, table)
    if error or not {"hotel_id", *FIELDS}.issubset(columns) or not hotel_id:
        return [], {**diagnostic, "status": "error" if error else "schema_drift"}
    selected = ", ".join(_safe_identifier(field) for field in FIELDS)
    order = "review_time DESC" + (", id DESC" if "id" in columns else "")
    try:
        cursor.execute(
            f"SELECT {selected} FROM {_safe_identifier(table)} "
            "WHERE hotel_id=%s AND review_time>=%s AND review_time<%s "
            f"ORDER BY {order}",
            (hotel_id, start.isoformat(), (end + dt.timedelta(days=1)).isoformat()),
        )
        rows = [{**row, "hotel_id": hotel_id} for row in cursor.fetchall()]
    except Exception as exc:
        return [], {**diagnostic, "status": "error", "error_type": type(exc).__name__}
    return rows, {
        **diagnostic, "status": "ok", "rows": len(rows), "hotel_filter_applied": True,
    }


def attach_recent_reviews(result: dict[str, Any], data: dict[str, Any]) -> None:
    item = next((row for row in (result.get("visual_diagnosis") or {}).get("items", [])
                 if int(row.get("standard_item_id") or 0) == 13), None)
    if item is None:
        return
    start, end = _window()
    diagnostic = next((source.get("tables", {}).get(DIAGNOSTIC)
                       for source in data.get("source_diagnostics", [])
                       if source.get("tables", {}).get(DIAGNOSTIC)), {})
    start_day = diagnostic.get("period_start") or start.isoformat()
    end_day = diagnostic.get("period_end") or end.isoformat()
    rows = []
    for row in (data.get("sections") or {}).get(SECTION, []):
        if str(row.get("hotel_id") or "") != str(data.get("hotel_id") or ""):
            continue
        day = str(row.get("review_time") or "")[:10]
        if start_day <= day <= end_day:
            rows.append({field: row.get(field) for field in FIELDS})
    rows.sort(key=lambda row: str(row.get("review_time") or ""), reverse=True)
    item["recent_reviews"] = {
        "period_start": start_day, "period_end": end_day,
        "period_days": 15, "includes_today": True,
        "data_status": diagnostic.get("status") or "not_integrated", "rows": rows,
    }


def _e(value: Any) -> str:
    return html.escape("—" if value is None or value == "" else str(value), quote=True)


def _reply(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "已回复"}:
        return "已回复"
    if text in {"0", "false", "no", "未回复"}:
        return "未回复"
    return "未知"


def _table(payload: dict[str, Any]) -> str:
    rows = payload.get("rows") or []
    start, end = payload.get("period_start"), payload.get("period_end")
    body = []
    for row in rows:
        values = [
            row.get("channel_source"), row.get("reviewer_name_masked"),
            row.get("review_score"), row.get("review_content"),
            str(row.get("review_time") or "").replace("T", " "),
            _reply(row.get("is_replied")),
        ]
        body.append("<tr>" + "".join(f"<td>{_e(v)}</td>" for v in values) + "</tr>")
    if not body:
        message = ("近15天暂无评论。" if payload.get("data_status") == "ok"
                   else "评论明细暂未取得，请检查数据来源。")
        body.append(f"<tr><td colspan='6'>{message}</td></tr>")
    headers = ("渠道", "用户名（脱敏）", "评分", "评论内容", "评论时间", "是否已回复")
    return (
        "<section id='meituan-recent-reviews'><h4>近15天评论明细（含当日）</h4>"
        f"<p>{_e(start)} 至 {_e(end)} · 共 {len(rows)} 条 · 按评论时间从新到旧展示</p>"
        "<div class='table-scroll'><table><thead><tr>"
        + "".join(f"<th>{name}</th>" for name in headers)
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div></section>"
    )


def patch_recent_reviews_html(document: str, result: dict[str, Any]) -> str:
    item = next((row for row in (result.get("visual_diagnosis") or {}).get("items", [])
                 if int(row.get("standard_item_id") or 0) == 13), {})
    payload = item.get("recent_reviews")
    if not payload:
        return document
    document = _DETAIL.sub("", document)
    document, count = _CARD.subn(
        lambda match: match.group(0).replace("</article>", _table(payload) + "</article>"),
        document, count=1,
    )
    if count and "id='MEITUAN_RECENT_REVIEWS_STYLE'" not in document:
        document = document.replace("</head>", STYLE + "</head>", 1)
    return document
