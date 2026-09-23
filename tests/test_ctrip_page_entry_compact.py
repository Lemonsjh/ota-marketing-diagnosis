from marketing_diagnosis.ctrip_page_entry_compact import patch_page_entry_html


def test_page_entry_content_is_rendered_as_compact_tags():
    document = "<html><head></head><body><article class='diagnosis-card' id='ctrip-rule-10'><div class='result-area'>old</div></article></body></html>"
    result = {
        "ctrip_items": {
            "10": {
                "fields": [
                    {"label": "酒店展示名称", "value": "测试酒店（高铁站店）"},
                    {"label": "门店后缀", "value": "高铁站店"},
                    {"label": "热门商圈词命中", "value": "高铁站"},
                ],
                "listing_content": {"推荐词": "服务热情，干净卫生", "短标签": "洗衣房，免费WiFi"},
            }
        }
    }

    output = patch_page_entry_html(document, result)

    assert "CTRIP_PAGE_ENTRY_COMPACT_STYLE" in output
    assert "class='ctrip-listing-tag'>服务热情" in output
    assert "class='ctrip-listing-tag'>免费WiFi" in output
    assert "old" not in output


def test_page_entry_patch_does_not_replace_meituan_module_10():
    document = "<html><head></head><body><article class='diagnosis-card' id='rule-10'><div class='result-area'>美团内容</div></article></body></html>"
    result = {"ctrip_items": {"10": {"listing_content": {"推荐词": "服务热情"}}}}

    output = patch_page_entry_html(document, result)

    assert output == document
