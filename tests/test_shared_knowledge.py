from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from marketing_diagnosis import shared_knowledge as kb
from marketing_diagnosis.knowledge_corpus import export_courses, load_courses
from marketing_diagnosis.knowledge_delivery import finalize_answer


class SharedKnowledgeTests(unittest.TestCase):
    def setUp(self):
        cache = Path(__file__).resolve().parents[1] / ".pytest_cache"
        cache.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=cache, prefix="knowledge_")
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.source, self.root, self.db = base / "drafts", base / "knowledge", base / "auth.sqlite"
        self.source.mkdir()
        codes = ["BG-001", "MK-001", "RM-001"] + [f"EC-{n:03d}" for n in range(1, 19)] + [f"OP-{n:03d}" for n in range(1, 22)]
        for code in codes:
            self.write_course(code)
        self.write_course("OP-018", issues=1)
        export_courses(self.source, self.root)
        config = {"agents": {"defaults": {"workspace": str(self.root),
                  "memorySearch": {"provider": "local", "sources": ["memory"]}},
                  "list": [{"id": kb.PROFILE}]}}
        (self.root / "openclaw.json").write_text(json.dumps(config))
        (self.root / "state/memory").mkdir(parents=True)
        with closing(sqlite3.connect(self.root / f"state/memory/{kb.PROFILE}.sqlite")) as con, con:
            con.execute("CREATE TABLE files(path TEXT, hash TEXT, source TEXT)")
            con.executemany("INSERT INTO files VALUES(?,?,'memory')", [(path, doc["sha256"]) for path, doc in load_courses(self.root).items()])
        self.gateway = base / "gateway.json"
        self.gateway_config = {"channels": {"feishu": {"enabled": True, "accounts": {
            "s14-a": {"enabled": True, "groupPolicy": "allowlist", "groupAllowFrom": ["oc_test_a", "oc_test_b", "oc_no_hotel"]},
            "s14-b": {"enabled": True, "groupAllowFrom": ["oc_test_a"]},
            "chief": {"enabled": True, "groupAllowFrom": ["oc_test_a", "oc_main_only"]}}}},
            "bindings": [{"type": "route", "agentId": "s14-operation-diagnosis",
                          "match": {"channel": "feishu", "accountId": account}} for account in ["s14-a", "s14-b"]]}
        self.write_gateway()
        self.env = patch.dict(os.environ, {"S14_KNOWLEDGE_ROOT": str(self.root), "S14_GATEWAY_CONFIG": str(self.gateway)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write_course(self, code, issues=0):
        content = (f'---\ndoc_id: "{code}"\ntitle: "课程{code}"\nscope: "shared"\n'
                   f'source_review_issue_count: {issues}\npublication_status: "draft"\n---\n'
                   f'# 课程{code}\n\n## 方法与条件\n\n课程讲解应结合市场和经营条件判断。\n')
        (self.source / f"{code}.md").write_text(content, encoding="utf-8")

    def write_gateway(self):
        self.gateway.write_text(json.dumps(self.gateway_config), encoding="utf-8")

    def search(self, chat="oc_test_a", sender="ou_test_reader", account="s14-a"):
        return kb.search_context("酒店动态定价怎么做？", chat_id=chat, sender_id=sender, account_id=account)

    def hit(self, **changes):
        result = {"path": "memory/OP-008.md", "score": 0.55, "startLine": 5, "endLine": 5,
                  "snippet": "伪造的工具摘要不应被使用"}
        return {**result, **changes}

    def test_export_all_shared_courses_including_review_flags(self):
        docs = load_courses(self.root)
        self.assertEqual(len(docs), 42)
        self.assertTrue((self.root / "memory/OP-018.md").exists())
        body = (self.root / "memory/OP-008.md").read_text(encoding="utf-8")
        self.assertNotIn("publication_status", body)
        self.assertTrue(body.startswith("# 课程"))
        self.assertIn('publication_status: "draft"', (self.source / "OP-008.md").read_text(encoding="utf-8"))

    def test_export_keeps_flagged_courses_and_rejects_duplicate_ids(self):
        self.write_course("OP-008", issues=1)
        self.assertEqual(export_courses(self.source, self.root.parent / "flagged")["documents"], 42)
        self.write_course("OP-008")
        (self.source / "duplicate.md").write_bytes((self.source / "OP-008.md").read_bytes())
        with self.assertRaises(ValueError):
            export_courses(self.source, self.root.parent / "duplicate")

    def test_export_does_not_include_hotel_private_material(self):
        self.write_course("XX-001")
        private = self.source / "XX-001.md"
        private.write_text(private.read_text(encoding="utf-8").replace('scope: "shared"', 'scope: "hotel_private"'), encoding="utf-8")
        target = self.root.parent / "shared_only"
        self.assertEqual(export_courses(self.source, target)["documents"], 42)
        self.assertFalse((target / "memory/XX-001.md").exists())

    def test_account_allowlist_is_checked_before_retrieval(self):
        with patch.object(kb, "_native_search") as native:
            for identity in [dict(chat="oc_unbound"), dict(chat="oc_main_only"),
                             dict(account="chief"), dict(account="s14-b", chat="oc_test_b"),
                             dict(sender=""), dict(account=""), dict(chat="user:ou_reader")]:
                self.assertEqual(self.search(**identity)["status"], "blocked", identity)
            native.assert_not_called()

    def test_whitelisted_group_needs_no_sqlite_hotel_binding(self):
        with patch.dict(os.environ, {"HOTEL_OTA_DB": str(self.db)}), patch.object(kb, "_native_search", return_value=[self.hit()]):
            self.assertEqual(self.search(chat="oc_no_hotel")["status"], "ok")
        self.assertFalse(self.db.exists())

    def test_missing_invalid_or_disabled_gateway_config_fails_closed(self):
        accounts = self.gateway_config["channels"]["feishu"]["accounts"]
        with patch.object(kb, "_native_search") as native:
            for field, value in [("enabled", False), ("groupPolicy", "disabled"),
                                 ("groupAllowFrom", "oc_test_a"), ("groupAllowFrom", ["*"])]:
                original = accounts["s14-a"][field]
                accounts["s14-a"][field] = value
                self.write_gateway()
                self.assertEqual(self.search()["status"], "blocked")
                accounts["s14-a"][field] = original
            self.gateway_config["channels"]["feishu"]["enabled"] = False
            self.write_gateway()
            self.assertEqual(self.search()["status"], "blocked")
            self.gateway.write_text("{broken", encoding="utf-8")
            self.assertEqual(self.search()["status"], "blocked")
            self.gateway.rename(self.gateway.with_suffix(".held"))
            self.assertEqual(self.search()["status"], "blocked")
            native.assert_not_called()

    def test_allowlist_removal_blocks_final_answer_with_valid_ticket(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            result = self.search()
        self.gateway_config["channels"]["feishu"]["accounts"]["s14-a"]["groupAllowFrom"] = []
        self.write_gateway()
        with patch("marketing_diagnosis.knowledge_delivery._gate") as gate:
            text = finalize_answer("课程方法。", result["ticket"], chat_id="oc_test_a", sender_id="ou_test_reader", account_id="s14-a")
            self.assertEqual(text, kb.AUTH_DENIED)
            gate.assert_not_called()

    def test_help_does_not_start_retrieval(self):
        with patch.object(kb, "_native_search") as native:
            result = kb.search_context("共享知识库", account_id="s14-a", chat_id="oc_test_a", sender_id="ou_test_reader")
        self.assertEqual(result["status"], "help")
        native.assert_not_called()

    def test_retrieval_uses_approved_file_lines_not_tool_snippet(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            result = self.search()
        self.assertEqual(result["status"], "ok")
        material = result["materials"][0]
        self.assertIn("结合市场", material["text"])
        self.assertNotIn("伪造", material["text"])
        self.assertEqual(material["section"], "方法与条件")
        self.assertNotIn("path", material)

    def test_unapproved_path_traversal_and_low_score_are_not_returned(self):
        hits = [self.hit(path="../../auth-profiles.json"), self.hit(path="memory/OP-999.md"), self.hit(score=0.1)]
        with patch.object(kb, "_native_search", return_value=hits):
            self.assertEqual(self.search()["status"], "no_match")

    def test_source_change_extra_memory_or_outdated_index_blocks_search(self):
        path = self.root / "MEMORY.md"
        path.write_text("其他酒店的会话记忆", encoding="utf-8")
        with patch.object(kb, "_native_search") as native:
            self.assertEqual(self.search()["status"], "unavailable")
            native.assert_not_called()
        # Move the fixture aside rather than deleting any external files.
        path.rename(self.root / "held-memory.txt")
        course = self.root / "memory/OP-008.md"
        course.write_text(course.read_text(encoding="utf-8") + "补充课程内容。\n", encoding="utf-8")
        self.assertEqual(self.search()["status"], "unavailable")

    def test_missing_index_blocks_without_creating_a_database(self):
        index = self.root / f"state/memory/{kb.PROFILE}.sqlite"
        index.rename(index.with_suffix(".held"))
        with patch.object(kb, "_native_search") as native:
            self.assertEqual(self.search()["status"], "unavailable")
            native.assert_not_called()
        self.assertFalse(index.exists())

    def test_fixed_directory_can_be_updated_without_a_new_release(self):
        source = self.source / "OP-008.md"
        source.write_text(source.read_text(encoding="utf-8") + "更新后的课程内容。\n", encoding="utf-8")
        self.assertEqual(export_courses(self.source, self.root)["documents"], 42)
        self.assertIn("更新后的课程内容", (self.root / "memory/OP-008.md").read_text(encoding="utf-8"))
        self.assertFalse((self.root / "READY.json").exists())
        self.assertFalse((self.root / "release.json").exists())

    def test_course_list_can_add_an_approved_document_without_code_changes(self):
        path = self.root / "memory/EC-099.md"
        path.write_text("# 新批准的课程\n\n课程正文。\n", encoding="utf-8")
        listing = self.root / "courses.json"
        listing.write_text(json.dumps(json.loads(listing.read_text()) + ["EC-099"]))
        docs = load_courses(self.root)
        self.assertEqual(len(docs), 43)
        with closing(sqlite3.connect(self.root / f"state/memory/{kb.PROFILE}.sqlite")) as con, con:
            con.execute("INSERT INTO files VALUES(?,?,'memory')", ("memory/EC-099.md", docs["memory/EC-099.md"]["sha256"]))
        self.assertEqual(len(kb._knowledge_documents(self.root)), 43)

    def test_ticket_cannot_cross_user_group_or_account_and_expires(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            result = self.search()
        ticket = result["ticket"]
        for chat, sender in [("oc_test_b", "ou_test_reader"), ("oc_test_a", "ou_other")]:
            with self.assertRaises(ValueError):
                kb.ticket_materials(self.root, ticket, chat, sender, "s14-a")
        with self.assertRaises(ValueError):
            kb.ticket_materials(self.root, ticket, "oc_test_a", "ou_test_reader", "s14-b")
        with patch.object(kb.time, "time", return_value=10**12), self.assertRaises(ValueError):
            kb.ticket_materials(self.root, ticket, "oc_test_a", "ou_test_reader", "s14-a")

    def test_tickets_replace_old_context_instead_of_growing_per_question(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            old, new = self.search(), self.search()
        with self.assertRaises(ValueError):
            kb.ticket_materials(self.root, old["ticket"], "oc_test_a", "ou_test_reader", "s14-a")
        self.assertTrue(kb.ticket_materials(self.root, new["ticket"], "oc_test_a", "ou_test_reader", "s14-a"))
        with closing(sqlite3.connect(self.root / "state/qa.sqlite")) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM contexts").fetchone()[0], 1)

    def test_final_reply_appends_real_sources_and_respects_output_gate(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            result = self.search()
        kwargs = dict(account_id="s14-a", chat_id="oc_test_a", sender_id="ou_test_reader")
        with patch("marketing_diagnosis.knowledge_delivery._gate", return_value=True):
            text = finalize_answer("先明确适用条件，再评估价格策略。", result["ticket"], **kwargs)
        self.assertIn("课程来源", text)
        self.assertIn("课程OP-008》·方法与条件", text)
        self.assertIn("仅作内部课程参考", text)
        self.assertNotIn(result["ticket"], text)
        with patch("marketing_diagnosis.knowledge_delivery._gate", return_value=False):
            self.assertNotIn("先明确", finalize_answer("先明确适用条件。", result["ticket"], **kwargs))

    def test_internal_fields_and_fake_execution_are_not_published(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            result = self.search()
        with patch("marketing_diagnosis.knowledge_delivery._gate", return_value=True):
            for draft in ["publication_status=draft", "已执行降价", "```json\n{}\n```", result["ticket"]]:
                self.assertIn("未通过内容检查", finalize_answer(draft, result["ticket"], account_id="s14-a",
                              chat_id="oc_test_a", sender_id="ou_test_reader"))

    def test_question_routing_separates_methods_reports_facts_and_execution(self):
        for query in ["酒店动态定价怎么做？", "浏览多但订单少，应该先排查什么？", "什么是RevPAR？", "如何分析酒店转化率？", "我们酒店怎么做会员运营？", "本店浏览多但订单少，一般怎么排查？"]:
            self.assertTrue(kb.is_knowledge_question(query), query)
        for query in ["帮我分析酒店经营情况", "生成诊断报告", "Excel模板", "本店今天订单多少？", "为什么昨天我店订单少", "当前我店房价为什么偏高？", "为什么我们酒店总是订单少？", "帮我直接降价", "房型名称：标准大床房"]:
            self.assertFalse(kb.is_knowledge_question(query), query)
