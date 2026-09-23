from __future__ import annotations

from marketing_diagnosis.manual_supplement import patch_manual_supplements


def _document() -> str:
    return """<html><head></head><body>
<div class='page' data-channel-view='meituan'><section id='overview'><div class='total-score-v17'><strong>40</strong><span>满分100分</span></div></section><section id='summary'></section><article id='rule-21' data-status='missing'><div class='title-score'><span>满分 1分</span></div><div class='result-area'>数据未取到</div></article></div>
<div class='page' data-channel-view='ctrip'><section id='overview'><div class='ctrip-overview-score'><strong>39.5</strong><span>满分100分</span></div></section><section id='ctrip-summary'></section><article id='rule-7' data-status='missing'><div class='title-score'><span>满分 8分</span></div><div class='result-area'>待接入</div></article></div>
</body></html>"""


def test_manual_supplement_is_scoped_to_requested_channel_items() -> None:
    output = patch_manual_supplements(
        _document(),
        {"hotel_id": "wyn", "period_start": "2026-08-01", "period_end": "2026-08-31"},
    )
    assert "S14_MANUAL_SUPPLEMENT_SCRIPT" in output
    assert "ids:[15,16,17,18,19,20,21,23]" in output
    assert "ids:[7,8,14,15,16,17,18,19,20,21]" in output
    assert "补充后得分" in output
    assert "人工补充（待复核）" in output
    assert "s14:manual-supplement:wyn:2026-08-01:2026-08-31" in output
    assert "view.querySelector('#ctrip-rule-'+id)||view.querySelector('#rule-'+id)" in output
    assert "评分条件" in output
    assert "信息完整度达到100得满分4分" in output
    assert "60至120单得2.5分" in output
    assert "闪住已参与得2分" in output
    assert "已开通且报名/生效状态有效得满分" in output
    assert "部分满足 / 自定义得分" in output
    assert "核验依据" not in output
    assert "data-manual-note" not in output


def test_manual_supplement_patch_is_idempotent_and_requires_dual_report() -> None:
    once = patch_manual_supplements(_document(), {})
    assert patch_manual_supplements(once, {}) == once
    plain = "<html><head></head><body>standalone</body></html>"
    assert patch_manual_supplements(plain, {}) == plain
