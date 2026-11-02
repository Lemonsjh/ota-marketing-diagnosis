import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from marketing_diagnosis import ctrip_flow, hotel_profiles, latest, reporting_current


class HotelChannelScopeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for hotel, channels in [("single", ["meituan"]), ("dual", ["meituan", "ctrip"])]:
            (root / (hotel + ".json")).write_text(json.dumps({
                "config_version": 1, "name": hotel, "channels": channels,
            }), encoding="utf-8")
        env = patch.dict(os.environ, {"HOTEL_OTA_HOTEL_CONFIG_DIR": str(root)})
        env.start()
        self.addCleanup(env.stop)

    def test_platform_scope_is_exact_and_explicit_disabled_request_is_rejected(self):
        self.assertEqual(hotel_profiles.scoped_platform("single", "multi"), "meituan")
        self.assertEqual(hotel_profiles.scoped_platform("dual", "multi"), "multi")
        with self.assertRaisesRegex(ValueError, "no_enabled_ota_channels"):
            hotel_profiles.scoped_platform("single", "ctrip")

    def test_database_loader_does_not_query_extra_ctrip_tables(self):
        with (
            patch.object(ctrip_flow.upstream, "load_mysql_dsn_dataset", return_value={}) as upstream,
            patch.object(ctrip_flow.base, "_connect_mysql", return_value=MagicMock()),
            patch("marketing_diagnosis.report_opening_data.load_opening", return_value={}),
            patch.object(ctrip_flow, "_load_flow_rows") as ctrip_query,
        ):
            ctrip_flow.load_mysql_dsn_dataset("mysql://test", hotel_id="single")
        self.assertEqual(upstream.call_args.kwargs["platform"], "meituan")
        ctrip_query.assert_not_called()

    def test_disabled_excel_rows_do_not_contribute_to_scores(self):
        data = {"hotel_id": "single", "sections": {
            "ota_funnel": [{"platform": "meituan", "orders": 3}, {"platform": "ctrip", "orders": 99}],
            "ctrip_promotion_status": [{"status": "JOINED"}],
            "hotel_performance_daily": [{"room_nights": 5}],
        }}
        with patch.object(latest, "_process", return_value={"final_score": 10,
                          "ctrip_items": {"1": {}}, "ctrip_summary": {"total_score": 50}}) as run:
            result = latest.process(data)
        sections = run.call_args.args[0]["sections"]
        self.assertEqual(sections["ota_funnel"], [{"platform": "meituan", "orders": 3}])
        self.assertEqual(sections["ctrip_promotion_status"], [])
        self.assertEqual(sections["hotel_performance_daily"], [{"room_nights": 5}])
        self.assertNotIn("ctrip_items", result)
        self.assertNotIn("ctrip_summary", result)
        self.assertEqual(result["enabled_channels"], ["meituan"])
        self.assertEqual(len(data["sections"]["ota_funnel"]), 2)

    def test_single_channel_report_never_builds_disabled_channel_view(self):
        with (
            patch.object(reporting_current, "build_meituan_html", return_value="美团报告") as meituan,
            patch.object(reporting_current, "_build_html") as dual,
        ):
            self.assertEqual(reporting_current.build_html({"hotel_id": "single"}), "美团报告")
        meituan.assert_called_once()
        dual.assert_not_called()
