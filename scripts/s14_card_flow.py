"""Trusted gateway adapter for S14 source choices. stdout is adapter JSON."""
import argparse
import json
import re
import secrets
import sqlite3
import sys
import time
from contextlib import closing

try:
    from . import s14_feishu_entry as entry
except ImportError:  # Direct script entry on the gateway host.
    import s14_feishu_entry as entry

from marketing_diagnosis.shared_knowledge import authorize_group


BUTTON = re.compile(r"^s14-choice:([a-f0-9]{32}):(database|excel)$")
EXPIRED = "这张卡片暂不可用，请由发起人使用最近一次诊断卡片，或重新发起诊断。"
WAIT_EXCEL = "已选择上传 Excel，请在 10 分钟内把文件发到本群，无需再次 @ 机器人。"
WAIT_DB = "已选择数据库，正在生成诊断报告。"


def selection_card(ticket, names):
    card = entry._source_selection_card(names)["card"]
    card["elements"][-1]["text"]["content"] = "也可以直接回复「数据库」或「上传Excel」。"
    card["elements"].append({"tag": "action", "actions": [
        {"tag": "button", "type": style, "text": {"tag": "plain_text", "content": label},
         "value": {"command": f"s14-choice:{ticket}:{choice}"}}
        for choice, label, style in (("database", "读取数据库", "primary"), ("excel", "上传 Excel", "default"))
    ]})
    return card


def handle(account, chat, sender, text, message_id="", *, operation="event", ticket=""):
    button = BUTTON.fullmatch(text)
    normalized = "".join(text.lower().split())
    choice = button[2] if button else (entry._normalize_choice(normalized)
                                       if normalized in entry.DATABASE_CHOICES | entry.EXCEL_CHOICES else None)
    if operation == "event" and not choice and (
            not entry._is_diagnosis_request(text) or entry._is_template_request(text)):
        return {"pass": True}
    authorize_group(chat, sender, account)
    hotel = entry._bound_hotel_id(chat)
    if not hotel:
        return {"text": "当前群还没有绑定酒店，请联系管理员。"}
    key = (account, chat, sender)
    now = time.time()
    with closing(sqlite3.connect(entry.STATE_DIR / "diagnosis_choices.sqlite", timeout=4)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("""CREATE TABLE IF NOT EXISTS choices (
            account TEXT, chat TEXT, sender TEXT, ticket TEXT, hotel TEXT, state TEXT,
            created REAL, message_id TEXT, prompt TEXT, names TEXT, card_id TEXT,
            PRIMARY KEY(account,chat,sender))""")
        db.execute("BEGIN IMMEDIATE")
        where = " WHERE account=? AND chat=? AND sender=?"
        row = db.execute("SELECT * FROM choices" + where, key).fetchone()
        if operation == "receipt":
            db.execute("UPDATE choices SET card_id=?" + where + " AND ticket=?", (message_id, *key, ticket))
            return {}
        if operation == "run":
            if not row or row["hotel"] != hotel or row["ticket"] != ticket or row["state"] != "database":
                return {}
            db.execute("UPDATE choices SET state='running'" + where, key)
        else:
            if not choice:
                if row and message_id and row["message_id"] == message_id:
                    return {}
                old = entry._get_flow_state(chat, sender) or {}
                names = entry._manual_names(text, old)
                ticket = secrets.token_hex(16)
                db.execute("INSERT OR REPLACE INTO choices VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (*key, ticket, hotel, "awaiting_source", now, message_id, text, json.dumps(names), ""))
                entry._set_flow_state("awaiting_source", chat_id=chat, sender_id=sender,
                                      extra={**entry._state_extra(old, names, sender), "source_card_ticket": ticket})
                return {"card": selection_card(ticket, names), "ticket": ticket, "fallback": entry.SOURCE_SELECTION_TEXT}
            if not row and not button:
                return {"pass": True}  # Existing text-only session.
            if (not row or row["hotel"] != hotel or (button and row["ticket"] != button[1])
                    or now - row["created"] > entry.STATE_TTL_SECONDS):
                return {"text": EXPIRED}
            if row["state"] != "awaiting_source":
                state = entry._get_flow_state(chat, sender) or {}
                if not button and state.get("state") == "awaiting_source" and not state.get("source_card_ticket"):
                    return {"pass": True}
                return {"text": "本次诊断已选择数据源，请查看群内的最新提示。"}
            state = entry._get_flow_state(chat, sender) or {}
            if state.get("source_card_ticket") != row["ticket"]:
                return {"text": EXPIRED} if button else {"pass": True}
            names = state.get("manual_room_type_names") or json.loads(row["names"])
            db.execute("UPDATE choices SET state=?, names=?" + where, (choice, json.dumps(names), *key))
            entry._set_flow_state("awaiting_excel" if choice == "excel" else "running_database",
                                  chat_id=chat, sender_id=sender, extra={"manual_room_type_names": names,
                                                                      "source_card_ticket": row["ticket"]})
            return {"text": WAIT_DB if choice == "database" else WAIT_EXCEL, "card_id": row["card_id"],
                    "job": row["ticket"] if choice == "database" else None}

    result = entry._run_database(row["prompt"], chat_id=chat, sender_id=sender, requested_hotel_id=hotel,
                                 manual_room_type_names=json.loads(row["names"]))
    return {"text": entry._result_payload(result, "text") or "本次未取得报告结果，请重新发起诊断。"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["event", "receipt", "run"])
    args = parser.parse_args()
    entry._load_env_file()
    try:
        response = handle(operation=args.operation, **json.load(sys.stdin))
    except PermissionError:
        response = {"text": "请在已授权的酒店诊断群中使用。"}
    print(json.dumps(response, ensure_ascii=False))
