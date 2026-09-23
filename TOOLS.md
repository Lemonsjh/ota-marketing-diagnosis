# Tools

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
