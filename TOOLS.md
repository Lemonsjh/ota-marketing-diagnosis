# Tools

For general course questions, follow `skills/hotel-shared-knowledge/SKILL.md`.
Retrieve with `scripts/s14_feishu_entry.py --knowledge-context --text QUESTION --chat-id CHAT_ID --sender-id SENDER_ID`;
its JSON is internal grounding only. Finalize the answer with the same identity and
`--knowledge-answer DRAFT --knowledge-ticket TICKET --format text`, then send that stdout verbatim.
Never use a raw memory CLI to bypass the entry's SQLite check.

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
