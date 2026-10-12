"""Chinese customer inputs mapped to the existing diagnosis sections."""
from __future__ import annotations

COMMON = {"酒店ID": "hotel_id", "快照时间": "snapshot_time"}
PERIOD = {"统计开始日期": "period_start_date", "统计结束日期": "period_end_date"}
PROMOTION = {
    **COMMON, **PERIOD, "酒店名称": "hotel_name", "推广投入": "spend_amount",
    "推广预订订单金额": "booking_order_amount", "推广预订订单数": "booking_order_count",
    "推广曝光": "exposure_count", "推广点击": "click_count", "推广ROI": "return_on_ad_spend",
}
EXTRA_FIELD_MAP = {
    "ctrip_business_metrics_funnel": {
        **COMMON, **PERIOD, "平台": "platform_scope", "列表曝光": "list_exposure",
        "同行列表曝光": "peer_list_exposure", "APP访客": "app_visitors",
        "同行APP访客": "peer_app_visitors", "详情访客": "detail_exposure",
        "同行详情访客": "peer_detail_exposure", "订单页访客": "order_filling_count",
        "同行订单页访客": "peer_order_filling_count", "提交订单": "order_submit_count",
        "同行提交订单": "peer_order_submit_count", "曝光到详情转化率(%)": "exposure_to_detail_rate_pct",
        "同行曝光到详情转化率(%)": "peer_exposure_to_detail_rate_pct",
        "详情到订单页转化率(%)": "detail_to_order_rate_pct",
        "同行详情到订单页转化率(%)": "peer_detail_to_order_rate_pct",
        "订单页到提交转化率(%)": "order_to_submit_rate_pct",
        "同行订单页到提交转化率(%)": "peer_order_to_submit_rate_pct",
        "曝光排名": "list_exposure_peer_rank", "访客排名": "detail_exposure_peer_rank",
        "转化排名": "detail_to_order_rate_peer_rank", "同行酒店总数": "competition_circle_hotel_count",
    },
    "ctrip_psi_score": {
        **COMMON, "业务日期": "business_date", "PSI总分": "psi_total_score",
        "基础分": "psi_basic_score", "基础分上限": "psi_basic_score_max",
        "奖励分": "psi_reward_score", "奖励分上限": "psi_reward_score_max",
        "扣分": "psi_deduction_score", "服务扣分": "service_deduction_score",
        "诚信扣分": "integrity_deduction_score", "财务扣分": "financial_deduction_score",
        "PSI排名": "psi_rank", "同行酒店总数": "psi_competition_circle_count",
    },
    "ctrip_psi_metric": {
        **COMMON, **PERIOD, "业务日期": "business_date", "指标名称": "metric_code",
        "指标值": "metric_value", "单位": "metric_unit", "权重(%)": "weight_pct",
        "指标得分": "psi_score", "同行排名": "competition_rank",
        "得分差距": "score_gap", "差距单位": "score_gap_unit",
    },
    "ctrip_promotion_performance_30d": PROMOTION,
    "ctrip_review_overview": {
        **COMMON, "点评平台": "channel_source", "点评评分": "review_score",
        "点评总数": "total_review_count", "未回复点评数": "unreplied_review_count",
        "差评数": "negative_review_count", "环境分": "environment_score",
        "设施分": "facility_score", "服务分": "service_score", "卫生分": "hygiene_score",
    },
    "ctrip_review_yesterday": {
        **COMMON, "点评平台": "platform_scope", "点评统计日期": "yesterday_review_date",
        "昨日新增点评数": "yesterday_new_review_count",
    },
    "ctrip_joined_rights": {**COMMON, "酒店名称": "hotel_name", "权益名称": "right_name"},
    "ctrip_promotion_status": {
        **COMMON, "配置项名称": "activity_code", "开通状态": "status", "状态说明": "status_detail",
        "参与房型数": "room_type_count", "近30天订单": "orders_30d",
        "对应指标值": "metric_value", "指标单位": "metric_unit", "覆盖平台": "platform_scope",
    },
    "ctrip_video_upload_status": {
        **COMMON, "视频类型": "video_type", "已上传数量": "uploaded_count", "需上传数量": "required_count",
    },
    "ctrip_goods_price_mapping": {
        **COMMON, "平台房型名称": "room_type_name", "平台商品名称": "ota_product_name", "房型ID": "room_type_id",
        "商品ID": "source_product_id", "挂牌价": "listed_price",
    },
    "ctrip_userprofile_distribution": {
        **COMMON, **PERIOD, "画像维度": "dimension_code", "分组名称": "bucket_label",
        "占比(%)": "rate_pct", "人数": "user_count", "指标值": "metric_value", "排序": "rank_position",
    },
    "ctrip_hourly_orders": {**COMMON, "近30天钟点房订单": "orders_30d"},
    "ctrip_competition_metrics_30d": {
        **COMMON, **PERIOD, "指标名称": "metric_code", "本店指标值": "hotel_value",
        "同行指标值": "competitor_avg", "同行排名": "competitor_rank", "同行酒店总数": "competition_circle_hotel_count",
    },
    "ctrip_promotion_activity": {
        **COMMON, "活动名称": "activity_name", "活动状态": "status",
    },
    "ctrip_promotion_activity_performance": {
        **COMMON, **PERIOD, "活动名称": "campaign_name", "近30天订单": "campaign_quantity",
        "预订订单数": "booking_order_count", "预订订单金额": "booking_order_amount",
    },
    "ctrip_business_metrics_loss": {
        **COMMON, **PERIOD, "业务日期": "business_date", "指标名称": "metric_name", "指标值": "metric_value",
        "同行均值": "peer_average", "同行排名": "competitor_rank",
    },
    "ctrip_order_loss_monthly": {
        **COMMON, "平台": "platform_scope", "统计月份": "period_month", "竞对酒店名称": "competitor_hotel_name",
        "流失订单数": "loss_order_count", "流失金额": "loss_order_amount", "流失排名": "ranking_position",
        "流失房型": "lost_room_types_text", "关注状态": "follow_status",
    },
}
FIELD_EXTENSIONS = {
    "promotion_finance": PROMOTION,
    "review_overviews": {
        "昨日新增点评数": "yesterday_new_review_count", "点评统计日期": "yesterday_review_date",
    },
}
PSI_CODES = {
    "历史间夜量": "historical_room_nights", "历史营业额": "historical_gmv",
    "历史成交率": "historical_deal_rate", "即时确认订单占比": "instant_confirm_order_rate",
    "消费者实惠分": "consumer_value", "房态良好度": "room_status_good_rate",
    "点评竞争指数": "review_competitiveness", "信息完整度": "information_completeness",
    "可取消率": "cancellation_rate",
}
ACTIVITY_CODES = {
    "信息完整度": "information_completeness", "积分联盟": "points_alliance", "优享会": "preferred_club",
    "商旅专享价": "business_travel_price", "闪住": "quick_check_inn", "钟点房": "hourly_room",
    "旅拍": "travel_photo", "详情页视频": "homepage_video", "挂牌/委托分销": "listing_pass",
    "列表页推荐词": "listing_recommendation_words", "列表页短标签": "listing_short_tags",
}
VIDEO_CODES = {"详情页视频": "hotel_detail_video", "列表页视频": "hotel_listing_video", "房型视频": "room_type_video"}
PROFILE_CODES = {
    "性别": "gender", "年龄段": "age_group", "本地/异地": "city_origin", "出行目的": "travel_type",
    "工作日/周末偏好": "travel_time", "消费价格带": "consumption_price", "提前预订天数": "booking_advance_days",
    "入住晚数": "stay_days", "主要预订时段": "orider_peak_time", "主要客源城市": "city_origin_top5",
}
LOSS_CODES = {"流失订单数": "loss_order_count", "流失订单金额": "loss_order_amount"}
COMPETITION_CODES = {
    "预订订单数": "booking_order_count", "预订销售额": "booking_sales_amount", "出租率": "occupancy_ratet",
    "APP转化率": "ctrip_app_conversion_ratet", "在店间夜": "inhouse_room_night", "APP访客": "ctrip_app_visitor_count",
}


def field_map(base):
    maps = {key: dict(value) for key, value in base.items()}
    maps.update(EXTRA_FIELD_MAP)
    for module, fields in FIELD_EXTENSIONS.items():
        maps[module].update(fields)
    return maps


def convert_extra(module, key, value):
    choices = COMPETITION_CODES if key == "metric_code" and module == "ctrip_competition_metrics_30d" else PSI_CODES if key == "metric_code" and module == "ctrip_psi_metric" else (
        ACTIVITY_CODES if key == "activity_code" else VIDEO_CODES if key == "video_type" and module.startswith("ctrip_")
        else PROFILE_CODES if key == "dimension_code" else LOSS_CODES if key == "metric_code" else {}
    )
    if key == "status" and module == "ctrip_promotion_status":
        choices = {"已配置": "CONFIGURED", "已报名": "JOINED", "未报名": "NOT_JOINED", "未参加": "NOT_JOINED",
                   "已参加": "JOINED", "未配置": "NOT_CONFIGURED", "已开通": "ENABLED", "未开通": "DISABLED", "待确认": "PENDING"}
    return choices.get(str(value).strip(), value)
