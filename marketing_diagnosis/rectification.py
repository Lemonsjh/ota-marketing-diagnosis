"""Build a browser-editable plan from the facts already present in an S14 report."""
from __future__ import annotations

import base64
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
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
    "C4": (16, "参与状态"),
    "C10": (10, "酒店展示名称|门店后缀|热门商圈词命中"),
    "C12": (8, "信息完整度|完整度结果"),
    "C14": (10, "推荐词|短标签|列表页推荐词 / 标签 / 卖点"),
    "C16": (13, "当前生效权益数|已报名权益|已报名权益数量|生效权益数|有效权益数"),
    "C18": (11, "在售房型数|已检测房型数|含后缀房型数|售卖房型数"),
    "C20": (20, "列表页视频"),
    "C24": (12, "评分"),
    "C25": (12, "点评条数"),
    "C29": (6, "PSI 服务质量总分|基础分|奖励分|总扣分"),
    "C31": (7, "参与状态|近30天扫码订单|日均扫码订单"),
    "C32": (9, "推广投入|推广订单|推广订单金额|近30天推广投入"),
    "M5": (18, "配置状态|开通状态|生效状态"),
    "M7": (19, "配置状态|开通状态|生效状态"),
    "M9": (10, "酒店展示名称|检测到的后缀|热门商圈词命中"),
    "M10": (21, "酒店官方预览视频"),
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
STATUS_LABELS = {"OPEN": "已开通", "CLOSED": "未开通", "RUNNING": "投放中", "PENDING": "状态待核实"}
SINGLE_STATUS = {"C4", "M5", "M7", "M12"}
VIDEO_SLOTS = {"C20": ("列表页视频", "列表页视频"), "M10": ("酒店官方预览视频", "首页预览视频")}
ROOM_REFERENCE = {"C13", "M14", "M19"}
CANCEL_TEXT = re.compile(r"(?:入住当天|入住前)?\d{1,2}:\d{2}前免费取消|入住前(?:可|免费)取消|不可取消")


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _field_text(value):
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return ""
    if isinstance(value, float):
        value = f"{value:.2f}".rstrip("0").rstrip(".")
    value = str(value).strip()
    return STATUS_LABELS.get(value, value) if value not in UNAVAILABLE and len(value) <= 250 else ""


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
    if item_code in SINGLE_STATUS:
        labels = ("参与状态", "开通状态", "配置状态")
        confirmed = {"已开通", "未开通", "已参与", "未参与", "已配置", "未配置"}
        state = next((facts[key] for key in labels if facts.get(key) in confirmed), None)
        return ("已带入部分现状", [state]) if state else ("待补资料", [])
    if item_code in VIDEO_SLOTS:
        field, slot = VIDEO_SLOTS[item_code]
        count = re.fullmatch(r"(\d+)(?:\s*/\s*(?:\d+|—))?", facts.get(field, ""))
        if not count:
            return "待补资料", []
        return "已带入部分现状", [("有" if int(count[1]) else "无") + slot]
    when = "、".join(sorted(dates)) or "报告周期 " + _period(result) + "（原指标日期未标注）"
    return "已带入部分现状", [f"{label} {value}" for label, value in facts.items()] + [when]


def _period(result):
    return f"{result.get('period_start') or '未标注'} 至 {result.get('period_end') or '未标注'}"


def _snapshot_reference(metrics, section, platform, labels):
    snapshot = metrics.get(section) or {}
    values = (snapshot.get("by_platform") or {}).get(platform) or {}
    if snapshot.get("status") in {"missing", "error", "stale"} or not values:
        return {}, None
    return ({label: values.get(field) for field, label in labels.items()},
            (snapshot.get("data_period") or {}).get("end"))


def _report_reference(code, platform, sources, result):
    """Use report snapshots for related facts, with the actual measurement named."""
    metrics = result.get("metrics") or {}
    rooms = [item for item in _values((metrics.get("room_types") or {}).get("items"))
             if item.get("platform") == platform and item.get("product_count")
             and item.get("room_type_name")]
    fields, day, anchor, title = {}, None, "", ""
    if code in {"C8", "C30"}:
        fields, day = _snapshot_reference(metrics, "price_ladder", platform, {
            "min_price": "最低商品挂牌价（元）", "max_price": "最高商品挂牌价（元）", "product_count": "商品数",
        })
        anchor, title = "topic-4", "商品价格快照"
    elif code == "M16":
        registered = (metrics.get("promotion") or {}).get("meituan_registered_activities") or {}
        names = [_field_text(name) for name in registered.get("names") or []]
        names = [name for name in names if name]
        day = registered.get("snapshot_time")
        report_end = _date(result.get("period_end"))
        snapshot_day = _date(day)
        if not names or (snapshot_day and report_end and not report_end - timedelta(days=30) <= snapshot_day <= report_end):
            return [], "", ""
        date_line = f"数据日期 {snapshot_day.isoformat()}" if snapshot_day else "报告周期 " + _period(result)
        return [f"报名活动 {len(names)} 项", "、".join(names), date_line], "topic-6", "美团报名活动"
    elif code == "C15":
        fields, day = _snapshot_reference(metrics, "promotion", platform, {
            "activity_count": "活动快照记录数", "activity_product_count": "活动商品记录数",
        })
        fields = {key: value for key, value in fields.items() if value}
        anchor, title = "topic-6", "活动与权益"
    elif code in ROOM_REFERENCE:
        names = list(dict.fromkeys(str(item["room_type_name"]) for item in rooms))
        if names:
            fields = {"商品快照房型数": len(names), "商品快照房型": "、".join(names[:6])}
            if len(names) > 6:
                fields["商品快照房型"] += f"等 {len(names)} 类"
        day = ((metrics.get("price_ladder") or {}).get("data_period") or {}).get("end")
        anchor, title = "rule-11", "房型名称与售卖房型"
    elif code == "C11":
        for item in _values(sources["C"].get(6, {}).get("metrics")):
            if item.get("metric_code") == "cancellation_rate" and item.get("connected"):
                value = _field_text(item.get("metric_value"))
                if value:
                    fields["PSI 可取消率（不含具体截止时间）"] = f"{value}%"
                    day = item.get("period_end_date") or item.get("business_date")
                break
        anchor, title = "rule-6", "PSI 服务质量分"
    elif code == "M13":
        rules = list(dict.fromkeys(
            match for item in rooms for name in item.get("product_names") or []
            for match in CANCEL_TEXT.findall(str(name))
        ))
        if rules:
            fields["商品名称标注（以具体退改条款为准）"] = "、".join(rules)
        day = ((metrics.get("price_ladder") or {}).get("data_period") or {}).get("end")
        anchor, title = "topic-4", "商品价格与预订条件"
    evidence = [f"{label} {_field_text(value)}" for label, value in fields.items() if _field_text(value)]
    if evidence:
        if _date(day) and _date(result.get("period_end")) and not (
            _date(result.get("period_end")) - timedelta(days=30) <= _date(day) <= _date(result.get("period_end"))
        ):
            return [], "", ""
        evidence.append(f"数据日期 {_date(day).isoformat()}" if _date(day) else "报告周期 " + _period(result))
    return evidence, anchor, title


def _promotion_balance_fact(code, result):
    if code == "M22":
        channel, label = "meituan", "推广通账户余额"
    elif code == "C32":
        channel, label = "ctrip", "金字塔账户余额"
    else:
        return None
    balance = (result.get("promotion_balances") or {}).get(channel) or {}
    captured = balance.get("snapshot_time")
    if not _date(captured):
        return None
    try:
        amount = Decimal(str(balance.get("total_balance")))
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    currency = balance.get("currency") or "CNY"
    money = f"¥{amount:,.2f}" if currency == "CNY" else f"{amount:,.2f} {currency}"
    return f"{label} {money}（采集时间 {captured}）"


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
    rows, stages = [], {}
    sheet_rows = dict.fromkeys(CHANNELS, 3)
    for record in json.loads((ASSETS / "items.json").read_text(encoding="utf-8")):
        code = record["id"]
        prefix = code[0]
        channel, name = CHANNELS[prefix]
        if channel not in enabled:
            continue
        if record["stage"]:
            stages[prefix] = record["stage"]
        sheet_rows[prefix] += 1
        row = {**record, "stage": stages.get(prefix, ""), "channel": name,
               "excel_row": sheet_rows[prefix], "status": "待补资料", "facts": []}
        anchor_prefix = "ctrip-" if prefix == "C" and "meituan" in enabled else ""
        if code in {"C9", "C28", "M25"}:
            row["status"] = "待业务确认"
        elif code in EVIDENCE:
            number, labels = EVIDENCE[code]
            item = sources[prefix].get(number, {})
            row["status"], row["facts"] = _evidence(item, code, labels, result)
            if row["facts"]:
                row["evidence"] = str(item.get("item_name") or record["title"])
                row["anchor"] = anchor_prefix + f"rule-{number}"
        if row["status"] == "待补资料":
            facts, anchor, title = _report_reference(code, channel, sources, result)
            if facts:
                row.update(status="已带入部分现状", facts=facts, evidence=title, anchor=anchor_prefix + anchor)
        if balance := _promotion_balance_fact(code, result):
            row["facts"].insert(0, balance)
            if row["status"] == "待补资料":
                row["status"] = "已带入部分现状"
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
