"""Build a browser-editable plan from the facts already present in an S14 report."""
from __future__ import annotations

import base64
from datetime import date, timedelta
from html import escape
from io import BytesIO
import json
import logging
import re
from pathlib import Path

from openpyxl import load_workbook

from marketing_diagnosis.channel_score_totals import _item_id, _keyed_values, _values


ASSETS = Path(__file__).parent / "templates" / "rectification"
PLAN_FILENAME = "rectification.html"
CHANNELS = {"C": ("ctrip", "携程"), "M": ("meituan", "美团")}
# Only link individual facts that support this action, never use a score as evidence.
EVIDENCE = {
    "C4": (16, "参与状态|近30天订单|成交金额"),
    "C10": (10, "酒店展示名称|门店后缀|热门商圈词命中"),
    "C12": (8, "信息完整度|完整度结果"),
    "C14": (10, "推荐词|短标签|列表页推荐词 / 标签 / 卖点"),
    "C16": (13, "当前生效权益数|已报名权益数量|生效权益数|有效权益数"),
    "C18": (11, "在售房型数|已检测房型数|含后缀房型数|售卖房型数"),
    "C20": (20, "详情页视频|列表页视频|房型视频"),
    "C24": (12, "评分"),
    "C25": (12, "点评条数"),
    "C29": (6, "PSI 服务质量总分|基础分|奖励分|总扣分"),
    "C31": (7, "参与状态|近30天扫码订单|日均扫码订单"),
    "C32": (9, "推广投入|推广订单|推广订单金额|近30天推广投入"),
    "M5": (18, "配置状态|开通状态|生效状态"),
    "M7": (19, "配置状态|开通状态|生效状态"),
    "M9": (10, "酒店展示名称|检测到的后缀|热门商圈词命中"),
    "M10": (21, "酒店官方视频|酒店官方预览视频|房型视频"),
    "M12": (20, "开通状态|生效状态"),
    "M17": (14, "已报名权益数量"),
    "M19": (11, "在售房型数|已检测房型数|含后缀房型数"),
    "M20": (6, "最新HOS分|近30天平均分|最新同行排名"),
    "M21": (7, "月扫码订单|近30天扫码订单"),
    "M22": (9, "推广状态|近30天推广投入|预订订单金额（元）"),
    "M23": (13, "美团点评条数|大众点评点评条数"),
    "M24": (13, "美团评分|大众点评评分|美团未回复点评数|大众点评未回复点评数"),
}
UNAVAILABLE = {"", "-", "—", "—/—", "暂无数据", "待接入", "待更新", "待计算", "待确认", "未取到", "数据缺失", "未配置数据"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _field_text(value):
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return ""
    value = str(value).strip()
    return value if value not in UNAVAILABLE and len(value) <= 250 else ""


def _evidence(item, item_code, labels, result):
    fields = item.get("fields") or []
    if item_code in {"C24", "C25"} and item.get("platforms"):
        key = "rating" if item_code == "C24" else "review_count"
        fields = [
            {"label": labels, "value": row.get(key), "data_date": row.get("snapshot_time")}
            for row in item["platforms"]
            if row.get("platform_key") == "ctrip" and row.get("data_status") in {"success", "zero", "partial"}
        ]
    dates = set()
    facts = {}
    has_conflict = False
    for field in _values(fields):
        label = str(field.get("label") or "")
        value = _field_text(field.get("value"))
        label_base = label.split("（取值日：", 1)[0].strip()
        if label_base not in labels.split("|") or not value:
            continue
        if label_base in facts and facts[label_base] != value:
            has_conflict = True
        facts.setdefault(label_base, value)
        dates.update(DATE_RE.findall(label))
        dates.update(DATE_RE.findall(str(field.get("data_date") or "")))
    if item_code in {"C4", "C31"} and facts.get("参与状态") == "未参与":
        if not _date(item.get("activity_snapshot_time")):
            return "待补资料", []
        # Non-participation does not establish an observed order or revenue count.
        facts = {"参与状态": "未参与"}
    for field in ("snapshot_time", "activity_snapshot_time", "business_date", "period_end", "period_end_date", "data_date"):
        if day := _date(item.get(field)):
            dates.add(day.isoformat())
    status = item.get("data_status")
    if has_conflict or status in {"conflict", "period_mismatch", "source_conflict"}:
        return "口径冲突", []
    cutoff = _date(result.get("period_end"))
    if status in {"stale", "expired"} or (dates and cutoff and date.fromisoformat(max(dates)) < cutoff - timedelta(days=30)):
        return "数据过期", []
    if status in {"missing", "manual_pending", "error", "query_error"} or not facts:
        return "待补资料", []
    when = "、".join(sorted(dates)) or "报告周期 " + _period(result) + "（原指标日期未标注）"
    return "已带入部分现状", [f"{label} {value}" for label, value in facts.items()] + [when]


def _period(result):
    return f"{result.get('period_start') or '未标注'} 至 {result.get('period_end') or '未标注'}"


def build_plan(result):
    enabled = result.get("enabled_channels")
    if enabled is None:
        from marketing_diagnosis.hotel_profiles import channels
        enabled = channels(result["hotel_id"])
    if enabled is None:
        platform = result.get("platform")
        enabled = [platform] if platform in {"meituan", "ctrip"} else ["meituan", "ctrip"]
    sources = {
        "C": {_item_id(item): item for item in _keyed_values(result.get("ctrip_items"))},
        "M": {_item_id(item): item for item in _values((result.get("visual_diagnosis") or {}).get("items"))},
    }
    rows = []
    for record in json.loads((ASSETS / "items.json").read_text(encoding="utf-8")):
        code = record["id"]
        prefix = code[0]
        channel, name = CHANNELS[prefix]
        if channel not in enabled:
            continue
        row = {**record, "channel": name, "status": "待补资料", "facts": []}
        if code in {"C9", "C28"}:
            row["status"] = "待业务确认"
        elif code == "C23":
            row["status"] = "暂不实施"
        elif code in EVIDENCE:
            number, labels = EVIDENCE[code]
            item = sources[prefix].get(number, {})
            row["status"], row["facts"] = _evidence(item, code, labels, result)
            if row["facts"]:
                row["evidence"] = str(item.get("item_name") or record["title"])
                row["anchor"] = ("ctrip-" if prefix == "C" and "meituan" in enabled else "") + f"rule-{number}"
        rows.append(row)
    return {
        "hotel": str(result.get("hotel_name") or result["hotel_id"]),
        "key": [str(result["hotel_id"]), str(result["run_id"]), _period(result)],
        "period": _period(result),
        "rows": rows,
    }


def _template(plan):
    workbook = load_workbook(ASSETS / "template.xlsx")
    selected = {row["channel"] for row in plan["rows"]}
    for sheet in list(workbook):
        if sheet.title not in selected:
            workbook.remove(sheet)
            continue
        sheet["A2"] = f"{plan['hotel']}  ·  {sheet.title}"
        sheet["A2"].data_type = "s"
        sheet["F1"] = f"诊断周期 {plan['period']}"
        sheet["F2"] = f"报告版本 {plan['key'][1]}"
        footer = 34 if sheet.title == "携程" else 26
        sheet.cell(footer, 1, "本表为整改草案。确认目标、措施、分工和验收条件后再执行。")
        sheet.cell(footer + 1, 1, "诊断现状与人工补充分别标注。空缺或口径冲突的项目请按状态补齐。")
    output = BytesIO()
    workbook.save(output)
    return base64.b64encode(output.getvalue()).decode("ascii")


def write_rectification(report_path, result):
    """Write the plan beside its diagnosis. Keep the report usable on export failure."""
    if not result.get("run_id") or not result.get("hotel_id"):
        return None
    try:
        plan = build_plan(result)
        if not plan["rows"]:
            return None
        plan["workbook"] = _template(plan)
        plan["report"] = Path(report_path).name
        payload = json.dumps(plan, ensure_ascii=False).replace("<", "\\u003c")
        layout = (ASSETS / "dialog.html").read_text(encoding="utf-8")
        layout = re.sub(r"\{\{(HOTEL|PERIOD|REPORT)\}\}", lambda match: escape({
            "HOTEL": plan["hotel"], "PERIOD": plan["period"], "REPORT": plan["report"],
        }[match[1]]), layout)
        style = (ASSETS / "dialog.css").read_text(encoding="utf-8")
        zip_js = (ASSETS / "fflate.js").read_text(encoding="utf-8")
        js = (ASSETS / "dialog.js").read_text(encoding="utf-8")
        page = (layout.replace("</head>", f"<style>{style}</style></head>", 1)
                .replace("</body>", f"<script type='application/json' id='rectification-data'>{payload}</script>"
                         + f"<script>{zip_js}</script><script>{js}</script></body>", 1))
        path = Path(report_path).with_name(PLAN_FILENAME)
        # Write the complete page before publishing its link.
        path.write_text(page, encoding="utf-8")
        return str(path)
    except Exception:
        logging.getLogger(__name__).exception("Could not prepare the optional rectification plan")
        return None


def link_rectification(document):
    link = f"<a id='rectification-open' class='btn' href='{PLAN_FILENAME}'>查看整改计划</a>"
    document = re.sub(r"(<button\b[^>]*>\s*导出报告\s*</button>)", lambda match: link + match[0],
                      document, count=1)
    if link not in document:
        document = document.replace("</header>", link + "</header>", 1)
    style = ("<style>#rectification-open{display:inline-flex;align-items:center;text-decoration:none;"
             "white-space:nowrap;margin-inline-end:.5rem}@media print{#rectification-open{display:none}}</style>")
    return document.replace("</head>", style + "</head>", 1)
