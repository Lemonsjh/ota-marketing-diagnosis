"""Stable imports for the current OTA marketing diagnosis runtime.

New code should import from this module instead of a numbered ``*_vN`` module.
Historical module names continue to work through ``_versioned_runtime``.
"""

from __future__ import annotations

from marketing_diagnosis.ctrip_flow import load_database_dataset, load_mysql_dsn_dataset
from marketing_diagnosis.ctrip_flow_rules import process
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


def normalize_dataset(raw):
    """Preserve Ctrip-specific records required by the final scoring rules."""
    result = _normalize_dataset(raw)
    sections = result.setdefault("sections", {})
    diagnostics = result.setdefault("diagnostics", {})
    for section in (
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
