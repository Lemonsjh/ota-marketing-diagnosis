import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import s14_card_flow as flow


class SourceChoiceTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(flow.entry, "STATE_DIR", Path(directory)))
        self.enterContext(patch.object(flow, "authorize_group"))
        self.hotel = self.enterContext(patch.object(flow.entry, "_bound_hotel_id", return_value="hotel"))

    def event(self, text, sender="user", **options):
        return flow.handle("account", "chat", sender, text, **options)

    def test_database_button_and_typed_reply_start_one_report(self):
        prompt = self.event("生成诊断报告")
        button = prompt["card"]["elements"][-1]["actions"][0]["value"]["command"]
        self.assertEqual(self.event(button, "another")["text"], flow.EXPIRED)
        job = self.event(button)["job"]
        self.assertNotIn("job", self.event("数据库"))
        with patch.object(flow.entry, "_run_database", return_value={"feishu_message": "报告链接"}) as run:
            self.assertEqual(self.event("", operation="run", ticket=job)["text"], "报告链接")
            self.assertEqual(self.event("", operation="run", ticket=job), {})
            self.assertEqual(run.call_args.kwargs["requested_hotel_id"], "hotel")
            run.assert_called_once()

    def test_excel_and_replaced_or_expired_card(self):
        old = self.event("生成诊断报告")
        latest = self.event("生成诊断报告")
        click = lambda prompt: prompt["card"]["elements"][-1]["actions"][1]["value"]["command"]
        self.assertEqual(self.event(click(old))["text"], flow.EXPIRED)
        with patch.object(flow.entry, "STATE_TTL_SECONDS", -1):
            self.assertEqual(self.event(click(latest))["text"], flow.EXPIRED)
        self.hotel.return_value = "other"
        self.assertEqual(self.event(click(latest))["text"], flow.EXPIRED)
        self.hotel.return_value = "hotel"
        self.assertEqual(self.event("上传 Excel")["text"], flow.WAIT_EXCEL)
        self.assertIn("awaiting_excel", flow.entry._get_flow_state("chat", "user").values())

    def test_existing_flow_and_other_intents(self):
        self.assertEqual(self.event("数据库"), {"pass": True})
        self.assertEqual(self.event("发个模板"), {"pass": True})
