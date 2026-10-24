"""Stable report entry point for the consolidated runtime."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from marketing_diagnosis import ctrip_reputation_report as _ctrip_reputation_report
from marketing_diagnosis import ctrip_flow_scoring_note as _ctrip_flow_scoring_note
from marketing_diagnosis import ctrip_psi_table_compact as _ctrip_psi_table_compact
from marketing_diagnosis import ctrip_rights_center_compact as _ctrip_rights_center_compact
from marketing_diagnosis.channel_score_totals import patch_channel_score_totals
from marketing_diagnosis.ctrip_manual_listing import patch_html
from marketing_diagnosis.ctrip_page_entry_compact import patch_page_entry_html
from marketing_diagnosis.meituan_market_report import patch_market_html
from marketing_diagnosis.meituan_recent_reviews import patch_recent_reviews_html
from marketing_diagnosis.manual_supplement import patch_manual_supplements
from marketing_diagnosis.visual_diagnosis import patch_video_upload_copy
from marketing_diagnosis.reporting_runtime_v52 import (
    build_ctrip_html as _build_ctrip_html,
    build_dual_channel_html as _build_dual_channel_html,
    build_html as _build_html,
    build_markdown as _build_markdown,
    build_meituan_html as _build_meituan_html,
    write_reports as _write_reports,
)


def _compact_business_travel(document: str) -> str:
    def compact(match: re.Match) -> str:
        card = match.group(0)
        if "ctrip-metric-v55" not in card:
            return card
        card = re.sub(r"(<div class='card-title'><h3>.*?</h3>)<p>.*?</p>", r"\1", card, flags=re.S)
        for pattern in (
            r"<div class='title-meta-item title-period'>.*?</div>",
            r"<span class='status-badge [^']*'>.*?</span>",
            r"<div class='ctrip-source-v55'>.*?</div>",
            r"<div class='notice'>.*?</div>",
        ):
            card = re.sub(pattern, "", card, flags=re.S)
        return re.sub(
            r"(<div class='ctrip-metric-v55'>.*?<strong\b[^>]*>.*?</strong>)\s*<span>.*?</span>",
            r"\1", card, flags=re.S,
        )

    return re.sub(r"<article\b[^>]*\bid='(?:ctrip-)?rule-16'[^>]*>.*?</article>", compact, document, flags=re.S)


def build_ctrip_html(result: dict[str, Any]) -> str:
    return patch_manual_supplements(
        patch_page_entry_html(patch_video_upload_copy(patch_html(patch_channel_score_totals(_compact_business_travel(_build_ctrip_html(result)), result), result)), result),
        result,
    )


def build_dual_channel_html(result: dict[str, Any]) -> str:
    return patch_recent_reviews_html(patch_market_html(patch_manual_supplements(
        patch_page_entry_html(patch_video_upload_copy(patch_html(patch_channel_score_totals(_compact_business_travel(_build_dual_channel_html(result)), result), result)), result),
        result,
    ), result), result)


def build_html(result: dict[str, Any]) -> str:
    return patch_recent_reviews_html(patch_market_html(patch_manual_supplements(
        patch_page_entry_html(patch_video_upload_copy(patch_html(patch_channel_score_totals(_compact_business_travel(_build_html(result)), result), result)), result),
        result,
    ), result), result)


def build_meituan_html(result: dict[str, Any]) -> str:
    return patch_recent_reviews_html(
        patch_market_html(patch_channel_score_totals(_build_meituan_html(result), result), result), result,
    )


def build_markdown(result: dict[str, Any]) -> str:
    from marketing_diagnosis.meituan_market_share import TITLE
    from marketing_diagnosis.meituan_exposure_monthly import _find_item
    from marketing_diagnosis.meituan_market_report import _num, _pct

    document = _build_markdown(result).replace("曝光数据分析", TITLE)
    item = _find_item((result.get("visual_diagnosis") or {}).get("items"), 3)
    if not item or "market_share" not in item:
        return document
    market = item["market_share"]
    yesterday = market["yesterday"]
    lines = [f"\n\n## 美团第三项：{TITLE}",
             f"昨日本店大盘份额（{yesterday['business_date']}）：{_pct(yesterday['share'])}",
             f"本店入住间夜：{_num(yesterday['own_room_nights'])}；大盘入住间夜（估算）：{_num(yesterday['market_room_nights'])}",
             "\n过去7天每日份额："]
    lines.extend(f"- {p['business_date']}：{_pct(p['share'])}" for p in market["daily_points"])
    lines.append("\n缺失数据不按0处理；大盘与份额为估算值。评分规则待确认。")
    return document + "\n\n".join(lines)


def write_reports(result: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    paths = _write_reports(result, output_dir)
    report_path = Path(paths["report_html"])
    report_path.write_text(build_html(result), encoding="utf-8")
    if paths.get("report_markdown"):
        Path(paths["report_markdown"]).write_text(build_markdown(result), encoding="utf-8")
    return paths


__all__ = [
    "build_ctrip_html",
    "build_dual_channel_html",
    "build_html",
    "build_markdown",
    "build_meituan_html",
    "write_reports",
]
