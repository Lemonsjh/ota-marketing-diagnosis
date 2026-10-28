import contextlib
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class KnowledgeEntryTests(unittest.TestCase):
    def setUp(self):
        cache = Path(__file__).resolve().parents[1] / ".pytest_cache"
        cache.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=cache, prefix="knowledge_entry_")
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"S14_STATE_DIR": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        script = Path(__file__).resolve().parents[1] / "scripts/s14_feishu_entry.py"
        spec = importlib.util.spec_from_file_location("knowledge_entry_test", script)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def run_entry(self, *args):
        stream = io.StringIO()
        with patch.object(sys, "argv", ["entry", *args]), contextlib.redirect_stdout(stream):
            self.assertEqual(self.module.main(), 0)
        return stream.getvalue()

    def test_context_is_explicit_json_without_touching_report_state(self):
        self.module._set_flow_state("awaiting_excel", chat_id="oc_a", sender_id="ou_a")
        with patch.object(self.module, "search_context", return_value={"status": "ok", "ticket": "test"}) as search:
            text = self.run_entry("--knowledge-context", "--text", "酒店定价怎么做？", "--chat-id", "oc_a", "--sender-id", "ou_a", "--account-id", "s14-a")
        self.assertEqual(json.loads(text)["status"], "ok")
        self.assertEqual(search.call_args.kwargs["chat_id"], "oc_a")
        self.assertEqual(search.call_args.kwargs["account_id"], "s14-a")
        self.assertNotIn("db", search.call_args.kwargs)
        self.assertEqual(self.module._get_flow_state("oc_a", "ou_a")["state"], "awaiting_excel")

    def test_finalize_is_verbatim_and_does_not_repeat_retrieval(self):
        with patch.object(self.module, "finalize_answer", return_value="已过闸门的正文") as final, patch.object(self.module, "search_context") as search:
            text = self.run_entry("--knowledge-answer", "草稿", "--knowledge-ticket", "ticket",
                                  "--chat-id", "oc_a", "--sender-id", "ou_a", "--account-id", "s14-a")
        self.assertEqual(text, "已过闸门的正文\n")
        self.assertEqual(final.call_args.args, ("草稿", "ticket"))
        self.assertEqual(final.call_args.kwargs["account_id"], "s14-a")
        search.assert_not_called()

    def test_method_does_not_trigger_report_and_report_still_selects_source(self):
        self.assertFalse(self.module._is_diagnosis_request("如何分析酒店转化率？"))
        self.assertTrue(self.module._is_diagnosis_request("帮我分析酒店经营情况"))
        text = self.run_entry("--text", "全面诊断", "--chat-id", "oc_a", "--sender-id", "ou_a", "--account-id", "s14-a")
        self.assertIn("请选择数据来源", text)

    def test_database_report_still_requires_sqlite_hotel_binding(self):
        db = Path(self.tmp.name) / "auth.sqlite"
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            con.executescript("CREATE TABLE chat_bindings(chat_id TEXT,hotel_id TEXT,status TEXT);"
                              "CREATE TABLE group_chat_bindings(chat_id TEXT,hotel_id TEXT,status TEXT);")
        with patch.object(self.module, "AUTH_DB_PATH", db), patch.object(self.module, "REQUIRE_BOUND_CHAT", True):
            with self.assertRaisesRegex(ValueError, "群未绑定酒店"):
                self.module._request_context("S14诊断", chat_id="oc_allowed_but_unbound", sender_id="ou_reader")
