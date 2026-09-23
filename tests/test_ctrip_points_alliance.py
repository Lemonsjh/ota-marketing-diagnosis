from marketing_diagnosis.ctrip_flow_rules import process


def test_inactive_points_alliance_treats_missing_orders_as_zero_and_hides_amount():
    result = process(
        {
            "sections": {
                "ctrip_promotion_status": [
                    {
                        "activity_code": "points_alliance",
                        "enabled": 0,
                        "status": "NOT_JOINED",
                        "orders_30d": None,
                        "metric_value": None,
                        "metric_unit": "amount",
                        "platform_scope": "ctrip",
                    }
                ]
            }
        }
    )

    item = result["ctrip_items"]["14"]
    fields = {field["label"]: field["value"] for field in item["fields"]}

    assert item["item_score"] == 0
    assert fields["报名状态"] == "未报名"
    assert fields["近30天订单"] == 0
    assert "成交金额" not in fields


def test_active_points_alliance_treats_missing_orders_as_zero():
    result = process(
        {
            "sections": {
                "ctrip_promotion_status": [
                    {
                        "activity_code": "points_alliance",
                        "enabled": 1,
                        "status": "JOINED",
                        "orders_30d": None,
                        "metric_value": 100,
                        "metric_unit": "amount",
                    }
                ]
            }
        }
    )

    item = result["ctrip_items"]["14"]
    fields = {field["label"]: field["value"] for field in item["fields"]}

    assert item["item_score"] == 1.8
    assert fields["近30天订单"] == 0
    assert "成交金额" not in fields
