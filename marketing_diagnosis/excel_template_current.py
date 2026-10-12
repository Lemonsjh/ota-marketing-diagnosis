"""Extend the customer workbook using the current report field definitions."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from marketing_diagnosis.excel_fields import (
    ACTIVITY_CODES, COMPETITION_CODES, EXTRA_FIELD_MAP, PROFILE_CODES, PROMOTION, PSI_CODES, VIDEO_CODES,
)

SPECS = (
    ("ctrip_business_metrics_funnel", "04_流量用户", "D. 携程近30天流量", "携程03/04 流量与漏斗", "与同行数据使用同一统计周期。转化率(%)填写10表示10%，不要填0.10。", 3),
    ("ctrip_userprofile_distribution", "04_流量用户", "E. 携程用户画像", "携程07 用户画像", "一行一个维度分组；占比(%)填0–100，如25表示25%。", 20),
    ("ctrip_psi_score", "04_流量用户", "F. 携程PSI总分", "携程06 PSI", "填写当前PSI快照；历史日期可新增行。未知扣分不要用0代替。", 6),
    ("ctrip_psi_metric", "04_流量用户", "G. 携程PSI明细", "携程06/08 PSI与信息完整度", "每个指标一行；信息完整度填写100表示100%。", 3),
    ("ctrip_promotion_performance_30d", "05_推广竞对", "C. 携程近30天推广", "携程09/10 推广与页面基础", "仅填写平台归因数据；ROI按平台原值填写，不使用PMS渠道收入。酒店名称填平台完整名称。", 3),
    ("ctrip_business_metrics_loss", "05_推广竞对", "D. 携程昨日流失", "携程05 流失诊断", "填写实际业务日期，一行一个指标：流失订单量或流失订单金额。", 3),
    ("ctrip_order_loss_monthly", "05_推广竞对", "E. 携程竞对流失", "携程05 竞对流失", "携程与去哪儿分开填写；每月每个竞对一行。", 15),
    ("ctrip_review_overview", "06_口碑权益", "C. 携程系点评概览", "携程12 口碑", "携程、去哪儿、同程旅行、智行分别填写；未知评分留空。", 4),
    ("ctrip_review_yesterday", "06_口碑权益", "D. 携程系昨日点评", "携程12 昨日新增点评", "填写实际点评统计日期和数量，不能把历史点评总数当作昨日新增数。", 4),
    ("ctrip_joined_rights", "06_口碑权益", "E. 携程已报名权益", "携程13 权益中心", "仅填写已报名权益，每项一行，不填写未报名项。", 10),
    ("ctrip_promotion_status", "07_配置视频挂冠", "D. 携程配置状态", "携程08/10/14–21 配置", "信息完整度填对应指标值；挂牌等级和列表页文案填状态说明。真实状态确定后才选是。", 4),
    ("ctrip_video_upload_status", "07_配置视频挂冠", "E. 携程视频数量", "携程20 详情页视频", "填写已上传/需上传数量；0表示确定未上传，未知请留空。", 3),
    ("ctrip_goods_price_mapping", "03_房型商品", "C. 携程售卖房型", "携程11 房型名称", "平台房型名称与平台商品名称分别填写，不能混用。", 15),
    ("ctrip_hourly_orders", "07_配置视频挂冠", "F. 携程钟点房订单", "携程18 钟点房", "填写近30天真实订单数，不确定时不要填写0。", 1),
    ("ctrip_competition_metrics_30d", "05_推广竞对", "F. 携程竞争圈指标", "携程05 竞争圈分析", "本店与同行必须同一近30天周期；排名分母填同行酒店总数。", 3),
    ("ctrip_promotion_activity", "07_配置视频挂冠", "G. 携程活动报名", "携程17 闪住与活动", "活动名称按平台原名称填写，如闪住、YOYO卡&扫码住专享促销；状态按平台原值填写。", 5),
    ("ctrip_promotion_activity_performance", "07_配置视频挂冠", "H. 携程活动效果", "携程活动效果", "按活动分别填写订单和金额，统计周期须一致。", 5),
)


def _new_block(module, sheet, title, page, note, blanks):
    fields = EXTRA_FIELD_MAP[module]
    headers = ["是否导入", "系统模块（勿改）", *fields]
    today = date.today()
    default = {"酒店ID": "demo_hotel", "业务日期": today, "快照时间": datetime.now().replace(microsecond=0),
               "统计开始日期": today - timedelta(days=29), "统计结束日期": today,
               "点评统计日期": today - timedelta(days=1)}
    choices = {}
    presets = [{}]
    if module == "ctrip_psi_metric":
        presets = [{"指标名称": name} for name in PSI_CODES]
        choices["指标名称"] = list(PSI_CODES)
    elif module == "ctrip_promotion_status":
        presets = [{"配置项名称": name, "开通状态": "待确认"} for name in ACTIVITY_CODES]
        choices = {"配置项名称": list(ACTIVITY_CODES), "开通状态": ["已开通", "未开通", "已报名", "未报名", "已参加", "未参加", "已配置", "未配置", "待确认"]}
    elif module == "ctrip_video_upload_status":
        presets = [{"视频类型": name} for name in VIDEO_CODES]
        choices["视频类型"] = list(VIDEO_CODES)
    elif module == "ctrip_userprofile_distribution":
        presets = [{"画像维度": name} for name in PROFILE_CODES]
        choices["画像维度"] = list(PROFILE_CODES)
    elif module == "ctrip_business_metrics_loss":
        presets = [{"指标名称": name} for name in ("流失订单量", "流失订单金额")]
        choices["指标名称"] = ["流失订单量", "流失订单金额"]
    elif module == "ctrip_competition_metrics_30d":
        presets = [{"指标名称": name} for name in COMPETITION_CODES]
        choices["指标名称"] = list(COMPETITION_CODES)
    for header in ("平台", "点评平台"):
        if header in fields:
            choices[header] = ["携程", "去哪儿", "同程旅行", "智行"] if header == "点评平台" else ["携程", "去哪儿"]
            default[header] = "携程"
    samples = [["否", module, *({**default, **preset}.get(label) for label in fields)] for preset in presets]
    return dict(sheet=sheet, title=title, module=module, page=page, headers=headers, samples=samples,
                blank_rows=blanks, note=note, validations=choices)


def update_blocks(blocks):
    # Keep old finance/revenue column aliases in the reader, not in new customer guidance.
    blocks = [block for block in blocks if block["module"] != "promotion_revenue"]
    for block in blocks:
        module = block["module"]
        if module == "promotion_finance":
            block.update(title="A. 美团近30天推广", headers=["是否导入", "系统模块（勿改）", *PROMOTION],
                         samples=[["否", module, *({"酒店ID": "demo_hotel", "统计开始日期": date.today()-timedelta(days=29),
                                    "统计结束日期": date.today(), "快照时间": datetime.now().replace(microsecond=0)}.get(h) for h in PROMOTION)]],
                         blank_rows=3, validations={}, note="同一近30天周期填写推广投入与推广预订订单金额，ROI由系统计算。不使用PMS房费收入替代。")
        elif module == "review_overviews":
            block["headers"].extend(["昨日新增点评数", "点评统计日期"])
            block["samples"] = [row + [None, date.today()-timedelta(days=1)] for row in block["samples"]]
            block["note"] = "每个平台一行；昨日新增点评数须同时填写点评统计日期，未知数量留空。"
        elif module == "order_loss_monthly":
            block["title"] = "B. 美团竞对订单流失"
        elif module == "ota_funnel":
            block["note"] = "美团日数据。携程流量请填本页专属区，不要混入此处。"
        elif module == "video_upload_status":
            block["note"] = "仅美团视频；携程视频请填写本页的携程视频数量区。"
    return blocks + [_new_block(*spec) for spec in SPECS]
