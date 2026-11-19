from __future__ import annotations

import unittest

from importlib import import_module


adapter = import_module("skills.s14-operation-diagnosis.runtime.feishu_adapter")


class FeishuReportAlignmentTests(unittest.TestCase):
    def _result(self):
        return {
            "hotel_id": "puyue",
            "hotel_name": "璞悦",
            "platform": "multi",
            "data_source": "hotel_puyue_mysql",
            "period_start": "2026-06-17",
            "period_end": "2026-07-16",
            "report_url": "http://example.test/report.html",
            # Deliberately wrong legacy values: the reply must ignore these.
            "final_score": 78,
            "metrics": {
                "ota_funnel": {
                    "exposure": 79072,
                    "views": 9550,
                    "paid_orders": 847,
                    "payment_conversion_rate": 0.089,
                }
            },
            "module_scores": [
                {
                    "module_id": "M03",
                    "module_name": "旧模块",
                    "score": 9.8,
                    "weight": 15,
                    "rate": 0.6,
                }
            ],
            "visual_diagnosis": {
                # Stale pre-patch aggregate: Feishu must use the final item
                # scores and bases rendered by the report instead.
                "normalized_score": 86.4,
                "raw_score": 76.0,
                "connected_base_score": 88.0,
                "items": [
                    {
                        "standard_item_id": 2,
                        "item_name": "房型 RevPAR 与低效房型",
                        "base_score": 8,
                        "item_score": 4.8,
                        "score_ratio": 0.6,
                        "participates_in_score": True,
                        "data_status": "success",
                        "fields": [
                            {"label": "全部在售房型数", "value": 10},
                            {"label": "低效房型数", "value": 2},
                            {"label": "低效房型占比", "value": 0.2},
                        ],
                    },
                    {
                        "standard_item_id": 4,
                        "item_name": "流量数据分析",
                        "base_score": 15,
                        "item_score": 9,
                        "score_ratio": 0.6,
                        "participates_in_score": True,
                        "data_status": "success",
                        "fields": [
                            {"label": "曝光人数", "value": 17187},
                            {"label": "浏览人数", "value": 1619},
                            {"label": "支付订单数", "value": 147},
                            {"label": "浏览-支付转化率", "value": 0.0908},
                        ],
                    },
                    {
                        "standard_item_id": 9,
                        "item_name": "推广数据",
                        "base_score": 8,
                        "item_score": 4.8,
                        "score_ratio": 0.6,
                        "participates_in_score": True,
                        "data_status": "success",
                        "fields": [
                            {"label": "推广状态", "value": "RUNNING"},
                            {"label": "近30天推广投入", "value": 2000},
                            {"label": "预订订单金额（元）", "value": 12000},
                            {"label": "ROI", "value": 6},
                        ],
                    },
                    {
                        "standard_item_id": 13,
                        "item_name": "口碑分析",
                        "base_score": 10,
                        "item_score": 8,
                        "score_ratio": 0.8,
                        "participates_in_score": True,
                        "data_status": "success",
                        "fields": [
                            {"label": "美团评分", "value": 4.8},
                            {"label": "美团点评条数", "value": 2337},
                            {"label": "昨日新增点评数", "value": 7},
                            {"label": "美团未回复点评数", "value": 9},
                        ],
                    },
                    {
                        "standard_item_id": 11,
                        "item_name": "房型名称卖点优化",
                        "base_score": 4,
                        "item_score": 0,
                        "score_ratio": 0,
                        "participates_in_score": True,
                        "data_status": "zero",
                        "fields": [],
                    },
                    {
                        "standard_item_id": 5,
                        "item_name": "用户来源数据",
                        "base_score": 0,
                        "item_score": None,
                        "score_ratio": None,
                        "participates_in_score": False,
                        "data_status": "missing",
                        "fields": [],
                    },
                ],
            },
        }

    def test_text_reply_summarizes_only_scored_report_items_without_numbers(self):
        result = self._result()
        result["visual_diagnosis"]["items"].append({
            "standard_item_id": 23, "item_name": "未知配置", "base_score": 1,
            "item_score": 0, "data_status": "missing",
        })
        reply = adapter.build_feishu_reply(result)
        self.assertIn("美团｜26.6/100", reply)
        self.assertIn("做得好：口碑分析", reply)
        self.assertIn("待改善：房型名称卖点优化", reply)
        self.assertIn(result["report_url"], reply)
        for old in ("11 房型", "13 口碑", "0/4", "17,187", "用户来源", "未知配置"):
            self.assertNotIn(old, reply)

    def test_card_and_text_use_the_enabled_channel_scores(self):
        result = self._result()
        result["enabled_channels"] = ["ctrip"]
        result["ctrip_items"] = {
            "3": {"item_name": "平台流量漏斗", "item_score": 2, "full_score": 10, "data_status": "success"},
            "8": {"item_name": "信息完整度", "item_score": 4, "full_score": 4, "data_status": "success"},
            "21": {"item_name": "挂牌", "item_score": None, "full_score": 1, "data_status": "manual_pending"},
        }
        card = adapter.build_feishu_card_reply(result)
        content = "\n".join(
            element["text"]["content"]
            for element in card["card"]["elements"]
            if element.get("tag") == "div"
        )
        for output in (adapter.build_feishu_reply(result), content):
            self.assertIn("携程｜10.8/100", output)
            self.assertIn("做得好：信息完整度", output)
            self.assertIn("待改善：平台流量漏斗", output)
            self.assertNotIn("美团", output)
            self.assertNotIn("挂牌", output)

    def test_dual_channel_totals_are_shown_separately(self):
        result = self._result()
        result["enabled_channels"] = ["meituan", "ctrip"]
        result["ctrip_summary"] = {"total_score": 18.2}
        reply = adapter.build_feishu_reply(result)
        self.assertIn("美团｜26.6/100", reply)
        self.assertIn("携程｜23/100", reply)


if __name__ == "__main__":
    unittest.main()
