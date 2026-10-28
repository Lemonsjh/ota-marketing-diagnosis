"""Finalize a grounded model answer through the existing Feishu output gate."""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

from .shared_knowledge import AUTH_DENIED, UNAVAILABLE, authorize_group, release_root, ticket_materials


def _gate(text: str) -> bool:
    path = Path(os.environ.get("S14_OUTPUT_GATE_FILE",
                "/opt/openclaw/workspaces/hotel-ota-ai/runtime/safety/feishu_output.py"))
    spec = importlib.util.spec_from_file_location("s14_knowledge_output_gate", path)
    if not spec or not spec.loader:
        return False
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.feishu_output_gate(source="feishu", content_kind="text", message=text).get("status") == "ok"


def finalize_answer(draft: str, ticket: str, *, db: Path, chat_id: str, sender_id: str) -> str:
    try:
        authorize_group(db, chat_id, sender_id)
    except PermissionError:
        return AUTH_DENIED
    try:
        materials = ticket_materials(release_root(), ticket, chat_id, sender_id)
        draft = draft.strip()
        forbidden = r"```|publication_status|source_review|prepared_at|doc_id|memory/courses|release\.json|(?:已|已经)(?:执行|写入|调价|降价|涨价|发布|删除|开通|关闭)"
        if not draft or len(draft) > 1800 or ticket in draft or re.search(forbidden, draft, re.I):
            return "知识回答未通过内容检查，请重新提出具体的课程问题。"
        references = list(dict.fromkeys(f"《{m['title']}》·{m['section']}" for m in materials))
        text = ("**运营知识参考**\n\n" + draft + "\n\n**课程来源**\n"
                + "\n".join(f"- {r}" for r in references)
                + "\n\n仅作内部课程参考；课程案例不作为本店实时数据、现行平台规则或执行指令。")
        return text if _gate(text) else "知识回答未通过输出检查，请重新提出具体的课程问题。"
    except Exception:
        return UNAVAILABLE
