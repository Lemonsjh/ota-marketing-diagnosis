# Tools

For general course questions, follow `skills/hotel-shared-knowledge/SKILL.md`.
Use the current trusted receiving bot account, group and sender; shared courses require that S14 account's group whitelist, not a SQLite hotel binding. Retrieve with `scripts/s14_feishu_entry.py --knowledge-context --text QUESTION --chat-id CHAT_ID --sender-id SENDER_ID --account-id ACCOUNT_ID`;
its JSON is internal grounding only. Finalize the answer with the same identity and
`--knowledge-answer DRAFT --knowledge-ticket TICKET --chat-id CHAT_ID --sender-id SENDER_ID --account-id ACCOUNT_ID --format text`, then send that stdout verbatim.
Never use a raw memory CLI to bypass the entry's account/group whitelist check.

Primary runtime commands:

```bash
python scripts/s14_feishu_entry.py --text 'S14诊断' --format text
```

```bash
ota-marketing-diagnosis diagnose-db --dsn-env S14_DB_DSN --hotel-id puyue --platform multi --output "$S14_REPORT_OUTPUT_DIR"
```

Expected outputs:

- `report.html`
- `report.json`
- `report.md`

Reports are generated under `S14_REPORT_OUTPUT_DIR` in a run-specific directory.
