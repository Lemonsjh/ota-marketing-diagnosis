"""Stable imports for the current OTA marketing diagnosis runtime.

New code should import from this module instead of a numbered ``*_vN`` module.
Historical module names continue to work through ``_versioned_runtime``.
"""

from __future__ import annotations

from marketing_diagnosis.ctrip_flow import load_database_dataset, load_mysql_dsn_dataset
from marketing_diagnosis.ctrip_flow_rules import process as _process
from marketing_diagnosis.data_v4 import normalize_dataset as _normalize_dataset
from marketing_diagnosis.excel_loader_v2 import load_excel_package
from marketing_diagnosis.reporting_current import (
    build_ctrip_html,
    build_dual_channel_html,
    build_html,
    build_markdown,
    build_meituan_html,
    write_reports,
)


def _row_channel(row):
    aliases = {"美团": "meituan", "dianping": "meituan", "大众点评": "meituan",
               "携程": "ctrip", "qunar": "ctrip", "去哪儿": "ctrip", "tongcheng": "ctrip", "zhixing": "ctrip"}
    for key in ("platform", "platform_scope", "channel_source", "source_platform"):
        name = str(row.get(key) or "").strip().lower()
        channel = aliases.get(name, name)
        if channel in {"meituan", "ctrip"}:
            return channel
    for key in ("source_table", "__source_table"):
        for channel in ("meituan", "ctrip"):
            if str(row.get(key) or "").startswith(channel + "_ota_"):
                return channel
    return None


def process(data):
    from marketing_diagnosis.hotel_profiles import channels
    enabled = channels(data.get("hotel_id"))
    if enabled is not None:
        sections = {}
        for section, rows in (data.get("sections") or {}).items():
            if any(section.startswith(c + "_") and c not in enabled for c in ("meituan", "ctrip")):
                sections[section] = []
            elif isinstance(rows, list):
                sections[section] = [r for r in rows if not isinstance(r, dict)
                                     or _row_channel(r) not in ({"meituan", "ctrip"} - enabled)]
            else:
                sections[section] = rows
        data = {**data, "sections": sections}
    result = _process(data)
    if enabled is not None:
        result["enabled_channels"] = sorted(enabled)
        if "ctrip" not in enabled:
            result = {k: v for k, v in result.items() if not k.startswith("ctrip_")}
    return result


def normalize_dataset(raw):
    """Preserve Ctrip-specific records required by the final scoring rules."""
    result = _normalize_dataset(raw)
    if isinstance(raw.get("report_opening"), dict):
        result["report_opening"] = raw["report_opening"]
    sections = result.setdefault("sections", {})
    diagnostics = result.setdefault("diagnostics", {})
    for section in (
        "meituan_market_room_nights",
        "meituan_review_daily_counts",
        "ctrip_promotion_activity",
        "ctrip_promotion_activity_performance",
        "ctrip_video_upload_status",
    ):
        rows = [dict(row) for row in (raw.get(section) or []) if isinstance(row, dict)]
        sections[section] = rows
        diagnostics[section] = {
            "section": section,
            "row_count": len(rows),
            "status": "ok" if rows else "empty",
        }
    return result


__all__ = [
    "build_ctrip_html",
    "build_dual_channel_html",
    "build_html",
    "build_markdown",
    "build_meituan_html",
    "load_database_dataset",
    "load_excel_package",
    "load_mysql_dsn_dataset",
    "normalize_dataset",
    "process",
    "write_reports",
]
