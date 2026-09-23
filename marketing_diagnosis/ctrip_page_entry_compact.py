from __future__ import annotations

import html
import re
from typing import Any


_ARTICLE_RE = re.compile(
    r"(?P<head><article class='diagnosis-card'(?=[^>]*\bid='ctrip-rule-10')[\s\S]*?<div class='result-area'>)"
    r"[\s\S]*?(?P<tail></div></article>)",
    re.IGNORECASE,
)

STYLE = """
<style id='CTRIP_PAGE_ENTRY_COMPACT_STYLE'>
.ctrip-page-entry-compact{display:grid;gap:16px}
.ctrip-page-entry-facts{display:grid;grid-template-columns:1.15fr 1.15fr 1.15fr;gap:12px}
.ctrip-page-entry-fact{min-width:0;padding:16px;border:1px solid #dce8e3;border-radius:12px;background:#fbfdfc}
.ctrip-page-entry-fact small,.ctrip-listing-block h4{display:block;margin:0;color:#6c7a83;font-size:13px;font-weight:800}
.ctrip-page-entry-fact strong{display:block;margin-top:9px;color:#26343d;font-size:20px;line-height:1.35;overflow-wrap:anywhere}
.ctrip-listing-block{padding:16px 18px;border:1px solid #cde6da;border-radius:12px;background:linear-gradient(135deg,#f7fcf9,#f1f8f4)}
.ctrip-listing-block-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.ctrip-listing-block-head span{padding:4px 9px;border-radius:999px;background:#dff2e8;color:#15704d;font-size:12px;font-weight:850;white-space:nowrap}
.ctrip-listing-group+.ctrip-listing-group{margin-top:12px;padding-top:12px;border-top:1px solid #dcece4}
.ctrip-listing-group label{display:block;margin-bottom:8px;color:#52616b;font-size:12px;font-weight:850}
.ctrip-listing-tags{display:flex;flex-wrap:wrap;gap:7px}
.ctrip-listing-tag{padding:6px 9px;border:1px solid #c9e2d5;border-radius:7px;background:#fff;color:#355447;font-size:13px;font-weight:700;line-height:1.35}
.ctrip-page-entry-source{margin:0;color:#74818a;font-size:12px;line-height:1.5}
@media(max-width:860px){.ctrip-page-entry-facts{grid-template-columns:1fr}.ctrip-listing-block-head{align-items:flex-start;flex-direction:column}}
</style>
"""


def _item(result: dict[str, Any]) -> dict[str, Any]:
    items = result.get("ctrip_items") or {}
    if isinstance(items, dict):
        value = items.get("10") or items.get(10)
        return value if isinstance(value, dict) else {}
    return {}


def _field(item: dict[str, Any], label: str) -> str:
    for row in item.get("fields") or []:
        if isinstance(row, dict) and str(row.get("label") or "").strip() == label:
            return str(row.get("value") or "").strip()
    return ""


def _tokens(value: str) -> list[str]:
    values = [part.strip() for part in re.split(r"[，,、；;|/]+", value) if part.strip()]
    return list(dict.fromkeys(values))


def _tags(value: str) -> str:
    values = _tokens(value)
    if not values:
        return "<span class='ctrip-listing-tag'>暂无配置</span>"
    return "".join(f"<span class='ctrip-listing-tag'>{html.escape(part)}</span>" for part in values)


def _content(item: dict[str, Any]) -> str:
    listing = item.get("listing_content") if isinstance(item.get("listing_content"), dict) else {}
    recommendation = str(listing.get("推荐词") or "")
    short_tags = str(listing.get("短标签") or "")
    facts = (
        ("酒店展示名称", _field(item, "酒店展示名称") or "待接入"),
        ("门店后缀", _field(item, "门店后缀") or "未识别"),
        ("热门商圈词命中", _field(item, "热门商圈词命中") or "未命中"),
    )
    fact_html = "".join(
        f"<div class='ctrip-page-entry-fact'><small>{html.escape(label)}</small><strong>{html.escape(value)}</strong></div>"
        for label, value in facts
    )
    return (
        "<div class='ctrip-page-entry-compact'>"
        f"<div class='ctrip-page-entry-facts'>{fact_html}</div>"
        "<section class='ctrip-listing-block'><div class='ctrip-listing-block-head'><h4>列表页展示内容</h4>"
        "<span>已读取配置</span></div>"
        f"<div class='ctrip-listing-group'><label>推荐词</label><div class='ctrip-listing-tags'>{_tags(recommendation)}</div></div>"
        f"<div class='ctrip-listing-group'><label>短标签</label><div class='ctrip-listing-tags'>{_tags(short_tags)}</div></div>"
        "<p class='ctrip-page-entry-source'>推荐词和短标签均已配置时，本项列表展示内容计 1 分。</p>"
        "</section></div>"
    )


def patch_page_entry_html(document: str, result: dict[str, Any]) -> str:
    item = _item(result)
    if not item or "CTRIP_PAGE_ENTRY_COMPACT_STYLE" in document:
        return document
    document, count = _ARTICLE_RE.subn(
        lambda match: match.group("head") + _content(item) + match.group("tail"),
        document,
        count=1,
    )
    if count:
        document = document.replace("</head>", STYLE + "</head>", 1)
    return document


__all__ = ["patch_page_entry_html"]
