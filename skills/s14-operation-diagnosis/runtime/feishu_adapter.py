from __future__ import annotations

from typing import Any

from marketing_diagnosis.channel_score_totals import (
    _item_id, _item_score, _keyed_values, _number, _values,
    ctrip_direct_total, meituan_direct_total, score_text,
)


def _enabled_channels(result: dict[str, Any]) -> list[str]:
    enabled = result.get("enabled_channels")
    if enabled is None:
        platform = result.get("platform")
        enabled = [platform] if platform in ("meituan", "ctrip") else ["meituan"]
        if platform not in ("meituan", "ctrip") and (result.get("ctrip_items") or result.get("ctrip_summary")):
            enabled.append("ctrip")
    return [channel for channel in ("meituan", "ctrip") if channel in enabled]


def _highlights(items: list[dict[str, Any]]) -> tuple[str, str]:
    ranked = []
    for item in items:
        if item.get("participates_in_score") is False or item.get("data_status") not in {"success", "zero"}:
            continue
        score = _item_score(item)
        base = _number(item.get("base_score") or item.get("full_score"))
        name = str(item.get("item_name") or "").strip()
        if name and score is not None and base and 0 <= score <= base:
            ranked.append((score / base, name))
    good = [name for ratio, name in sorted(ranked, key=lambda row: -row[0]) if ratio >= 0.8]
    weak = [name for ratio, name in sorted(ranked, key=lambda row: row[0]) if ratio < 0.6]
    return "、".join(good[:3]) or "暂无突出项", "、".join(weak[:3]) or "暂无明显弱项"


def _channel_blocks(result: dict[str, Any]) -> list[str]:
    meituan = list(_values((result.get("visual_diagnosis") or {}).get("items")))
    ctrip = _keyed_values(result.get("ctrip_items"))
    ctrip_ids = {_item_id(item) for item in ctrip}
    ctrip += [item for item in meituan if _item_id(item) in {1, 2} - ctrip_ids]
    blocks = []
    for channel in _enabled_channels(result):
        if channel == "meituan":
            name, items, total = "美团", meituan, meituan_direct_total(result)
        else:
            name, items, total = "携程", ctrip, ctrip_direct_total(result, exclude_ids={21})
        good, weak = _highlights(items)
        blocks.append(f"**{name}｜{score_text(total)}/100**\n做得好：{good}\n待改善：{weak}")
    return blocks


def _title(result: dict[str, Any]) -> str:
    hotel = result.get("hotel_name") or result.get("hotel_id") or "酒店"
    return f"{hotel}｜OTA 诊断概览"


def _report_links(result: dict[str, Any]) -> list[tuple[str, str]]:
    links = []
    if report_url := result.get("report_url"):
        links.append(("查看完整诊断报告", report_url))
    plan_url = result.get("rectification_url") or ""
    if plan_url.startswith(("https://", "http://")):
        links.append(("查看整改计划", plan_url))
    return links


def build_feishu_reply(result: dict[str, Any]) -> str:
    channel_names = "、".join("美团" if c == "meituan" else "携程" for c in _enabled_channels(result))
    lines = [_title(result)]
    if channel_names:
        lines.append(f"渠道：{channel_names}")
    lines.extend(_channel_blocks(result))
    lines.extend(f"{label}：{url}" for label, url in _report_links(result))
    return "\n\n".join(lines)


def build_feishu_card_reply(result: dict[str, Any]) -> dict[str, Any]:
    elements: list[dict[str, Any]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": block}}
        for block in _channel_blocks(result)
    ]
    if links := _report_links(result):
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": label},
                        "type": "primary" if index == 0 else "default",
                        "url": url,
                    }
                    for index, (label, url) in enumerate(links)
                ],
            }
        )
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": _title(result),
                },
            },
            "elements": elements,
        },
    }


__all__ = [
    "build_feishu_card_reply",
    "build_feishu_reply",
]
