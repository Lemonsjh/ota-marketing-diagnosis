"""Current compact template reader; legacy files remain readable."""
from __future__ import annotations

import re
import math
from datetime import date
from marketing_diagnosis.customer_excel_loader import (
    IMPORT_HEADER, MODULE_HEADER, MODULE_FIELD_MAP, _is_imported, _iso_date,
    _normalize_value, _text, is_customer_excel_template,
)
from marketing_diagnosis.excel_fields import convert_extra, field_map

FIELDS = field_map(MODULE_FIELD_MAP)
TITLE = re.compile(r"〔\s*系统模块\s*[：:]\s*([^〕]+)〕")


def load_customer_excel_workbook(workbook):
    dataset, context, rejected = {}, {}, []
    imported = skipped = 0
    for sheet in workbook.worksheets:
        headers, active_module = None, ""
        for row_number, raw in enumerate(sheet.iter_rows(values_only=True), 1):
            texts = [_text(value) for value in raw]
            title = next((TITLE.search(value) for value in texts if TITLE.search(value)), None)
            if title:
                active_module = title.group(1).strip()
                headers = None
                continue
            if IMPORT_HEADER in texts and MODULE_HEADER in texts:
                headers = texts
                continue
            if not headers:
                continue
            record = {headers[i]: value for i, value in enumerate(raw) if i < len(headers) and headers[i]}
            if not _is_imported(record.get(IMPORT_HEADER)):
                skipped += 1
                continue
            module = _text(record.get(MODULE_HEADER)) or active_module
            fields = FIELDS.get(module)
            if not fields:
                rejected.append({"sheet": sheet.title, "row": row_number, "reason": "unknown_module"})
                continue
            converted = {}
            for label, key in fields.items():
                value = record.get(label)
                if value in (None, ""):
                    continue
                value = convert_extra(module, key, value)
                if module == "ctrip_promotion_status" and key == "status":
                    converted[key] = value
                else:
                    converted[key] = _normalize_value(module, key, value, record)
                if isinstance(converted[key], date):
                    converted[key] = converted[key].isoformat()
                if key in {"period_start", "period_end", "business_date", "period_start_date", "period_end_date", "yesterday_review_date"}:
                    converted[key] = _iso_date(converted[key])
                if label.endswith("(%)") and isinstance(value, str) and value.endswith("%"):
                    converted[key] = float(value[:-1])
                elif label.endswith("(%)") and record[label] is not None and isinstance(value, (int, float)):
                    # Percentage-labelled inputs are explicitly 0–100, not fractions.
                    converted[key] = value
                    if hasattr(sheet, "cell"):
                        column = headers.index(label) + 1
                        if "%" in sheet.cell(row_number, column).number_format:
                            converted[key] = value * 100
            required = {"hotel_id"}
            if module == "promotion_finance" and "推广投入" in headers:
                required.update({"spend_amount", "booking_order_amount", "period_start_date", "period_end_date"})
            if module == "ctrip_promotion_performance_30d":
                required.update({"spend_amount", "booking_order_amount", "period_start_date", "period_end_date", "return_on_ad_spend"})
            if converted.get("yesterday_new_review_count") is not None:
                required.add("yesterday_review_date")
            if required - converted.keys():
                rejected.append({"sheet": sheet.title, "row": row_number, "reason": "missing_required_input"})
                continue
            numeric_inputs = {"spend_amount", "booking_order_amount", "return_on_ad_spend",
                              "yesterday_new_review_count", "uploaded_count", "required_count"}
            try:
                for key in numeric_inputs & converted.keys():
                    number = float(str(converted[key]).replace(",", ""))
                    if not math.isfinite(number) or number < 0:
                        raise ValueError
                    converted[key] = number
            except (TypeError, ValueError):
                rejected.append({"sheet": sheet.title, "row": row_number, "reason": "invalid_number"})
                continue
            if not converted:
                rejected.append({"sheet": sheet.title, "row": row_number, "reason": "empty_data"})
                continue
            if module == "ctrip_promotion_status":
                converted["activity_name"] = record.get("配置项名称")
            if module == "basic_info":
                context.update(converted)
            else:
                converted["source_table"] = f"Excel：{sheet.title}/{module}"
                dataset.setdefault(module, []).append(converted)
            imported += 1
    dataset["__excel_context__"] = context
    hotel_ids = {str(row["hotel_id"]) for rows in dataset.values() if isinstance(rows, list) for row in rows if row.get("hotel_id")}
    if context.get("hotel_id"):
        hotel_ids.add(str(context["hotel_id"]))
    if len(hotel_ids) > 1:
        raise ValueError("Excel填报错误：所有导入区域必须属于同一家酒店，请核对酒店ID。")
    dataset["__source_diagnostics__"] = [{
        "loader": "customer_excel_current", "status": "partial" if rejected else "ok",
        "imported_rows": imported, "skipped_rows": skipped, "rejected_rows": rejected,
        "unsupported_modules": sorted({item['reason'] for item in rejected if item['reason'] == 'unknown_module'}),
    }]
    if rejected:
        positions = "、".join(f"{item['sheet']}第{item['row']}行" for item in rejected[:5])
        raise ValueError(f"Excel填报错误：{positions}缺少有效模块或必填数据，请检查选择导入的行。")
    return dataset
