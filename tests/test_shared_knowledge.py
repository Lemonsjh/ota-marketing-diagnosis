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
from marketing_diagnosis.knowledge_corpus import APPROVED_COURSES, RELEASE_VERSION, export_courses, load_release
from marketing_diagnosis.knowledge_delivery import finalize_answer


class SharedKnowledgeTests(unittest.TestCase):
    def setUp(self):
        cache = Path(__file__).resolve().parents[1] / ".pytest_cache"
        cache.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=cache, prefix="knowledge_")
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.source, self.root, self.db = base / "drafts", base / "release", base / "auth.sqlite"
        self.source.mkdir()
        for code in sorted(APPROVED_COURSES):
            self.write_course(code)
        self.write_course("OP-018", issues=1)
        export_courses(self.source, self.root)
        config = {"agents": {"defaults": {"workspace": str(self.root / "workspace"),
                  "memorySearch": {"provider": "local", "sources": ["memory"]}},
                  "list": [{"id": kb.PROFILE}]}}
        (self.root / "openclaw.json").write_text(json.dumps(config))
        (self.root / "READY.json").write_text(json.dumps({"version": RELEASE_VERSION, "ready": True, "files": 22}))
        with closing(sqlite3.connect(self.db)) as con, con:
            con.executescript("""
            CREATE TABLE auth_backend_state(backend_name TEXT,status TEXT);
            INSERT INTO auth_backend_state VALUES('feishu_active_auth','active');
            CREATE TABLE chat_bindings(chat_id TEXT, hotel_id TEXT, chat_type TEXT, status TEXT);
            INSERT INTO chat_bindings VALUES('oc_test_a','hotel_a','group','active');
            INSERT INTO chat_bindings VALUES('oc_test_b','hotel_b','group','active');
            CREATE TABLE group_chat_bindings(chat_id TEXT, hotel_id TEXT,status TEXT);
            """)
        self.env = patch.dict(os.environ, {"S14_KNOWLEDGE_ROOT": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write_course(self, code, issues=0):
        content = (f'---\ndoc_id: "{code}"\ntitle: "课程{code}"\nscope: "shared"\n'
                   f'source_review_issue_count: {issues}\npublication_status: "draft"\n---\n'
                   f'# 课程{code}\n\n## 方法与条件\n\n课程讲解应结合市场和经营条件判断。\n')
        (self.source / f"{code}.md").write_text(content, encoding="utf-8")

    def search(self, chat="oc_test_a", sender="ou_test_reader"):
        return kb.search_context("酒店动态定价怎么做？", db=self.db, chat_id=chat, sender_id=sender)

    def hit(self, **changes):
        result = {"path": "memory/courses/OP-008.md", "score": 0.55, "startLine": 5, "endLine": 5,
                  "snippet": "伪造的工具摘要不应被使用"}
        return {**result, **changes}

    def test_export_exact_approved_set_and_remove_management_fields(self):
        docs = load_release(self.root)
        self.assertEqual(len(docs), 22)
        self.assertFalse((self.root / "workspace/memory/courses/OP-018.md").exists())
        body = (self.root / "workspace/memory/courses/OP-008.md").read_text(encoding="utf-8")
        self.assertNotIn("publication_status", body)
        self.assertTrue(body.startswith("# 课程"))
        self.assertIn('publication_status: "draft"', (self.source / "OP-008.md").read_text(encoding="utf-8"))

    def test_export_rejects_missing_flagged_or_duplicate_approved_course(self):
        self.write_course("OP-008", issues=1)
        with self.assertRaises(ValueError):
            export_courses(self.source, self.root.parent / "blocked")
        self.write_course("OP-008")
        (self.source / "duplicate.md").write_bytes((self.source / "OP-008.md").read_bytes())
        with self.assertRaises(ValueError):
            export_courses(self.source, self.root.parent / "duplicate")

    def test_auth_happens_before_retrieval_and_missing_db_is_not_created(self):
        with patch.object(kb, "_native_search") as native:
            self.assertEqual(self.search(chat="oc_unbound")["status"], "blocked")
            missing = self.root / "missing.sqlite"
            result = kb.search_context("酒店定价怎么做？", db=missing, chat_id="oc_test_a", sender_id="ou_test")
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(missing.exists())
            native.assert_not_called()

    def test_missing_sender_and_inactive_auth_fail_closed(self):
        self.assertEqual(self.search(sender="")["status"], "blocked")
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE auth_backend_state SET status='inactive'")
        with patch.object(kb, "_native_search") as native:
            self.assertEqual(self.search()["status"], "blocked")
            native.assert_not_called()

    def test_help_does_not_start_retrieval(self):
        with patch.object(kb, "_native_search") as native:
            result = kb.search_context("共享知识库", db=self.db, chat_id="oc_test_a", sender_id="ou_test_reader")
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
        hits = [self.hit(path="../../auth-profiles.json"), self.hit(path="memory/courses/OP-018.md"), self.hit(score=0.1)]
        with patch.object(kb, "_native_search", return_value=hits):
            self.assertEqual(self.search()["status"], "no_match")

    def test_source_change_extra_memory_or_unready_index_blocks_search(self):
        path = self.root / "workspace/MEMORY.md"
        path.write_text("其他酒店的会话记忆", encoding="utf-8")
        with patch.object(kb, "_native_search") as native:
            self.assertEqual(self.search()["status"], "unavailable")
            native.assert_not_called()
        # Move the fixture aside rather than deleting any external files.
        path.rename(self.root / "held-memory.txt")
        course = self.root / "workspace/memory/courses/OP-008.md"
        course.write_text("changed", encoding="utf-8")
        self.assertEqual(self.search()["status"], "unavailable")

    def test_ticket_cannot_cross_user_or_hotel_and_expires(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            result = self.search()
        ticket = result["ticket"]
        for chat, sender in [("oc_test_b", "ou_test_reader"), ("oc_test_a", "ou_other")]:
            with self.assertRaises(ValueError):
                kb.ticket_materials(self.root, ticket, chat, sender)
        with patch.object(kb.time, "time", return_value=10**12), self.assertRaises(ValueError):
            kb.ticket_materials(self.root, ticket, "oc_test_a", "ou_test_reader")

    def test_tickets_replace_old_context_instead_of_growing_per_question(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            old, new = self.search(), self.search()
        with self.assertRaises(ValueError):
            kb.ticket_materials(self.root, old["ticket"], "oc_test_a", "ou_test_reader")
        self.assertTrue(kb.ticket_materials(self.root, new["ticket"], "oc_test_a", "ou_test_reader"))
        with closing(sqlite3.connect(self.root / "retrieval_tickets.sqlite")) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM contexts").fetchone()[0], 1)

    def test_final_reply_appends_real_sources_and_respects_output_gate(self):
        with patch.object(kb, "_native_search", return_value=[self.hit()]):
            result = self.search()
        kwargs = dict(db=self.db, chat_id="oc_test_a", sender_id="ou_test_reader")
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
            for draft in ["publication_status=draft", "已执行降价", "```json\n{}\n```"]:
                self.assertIn("未通过内容检查", finalize_answer(draft, result["ticket"], db=self.db,
                              chat_id="oc_test_a", sender_id="ou_test_reader"))

    def test_question_routing_separates_methods_reports_facts_and_execution(self):
        for query in ["酒店动态定价怎么做？", "浏览多但订单少，应该先排查什么？", "什么是RevPAR？", "如何分析酒店转化率？"]:
            self.assertTrue(kb.is_knowledge_question(query), query)
        for query in ["帮我分析酒店经营情况", "生成诊断报告", "Excel模板", "本店今天订单多少？", "为什么昨天我店订单少", "帮我直接降价", "房型名称：标准大床房"]:
            self.assertFalse(kb.is_knowledge_question(query), query)
