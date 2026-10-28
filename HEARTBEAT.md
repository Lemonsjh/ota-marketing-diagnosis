# Heartbeat

For diagnosis report checks, verify:

```bash
python -c "import pymysql, openpyxl; print('deps ok')"
python scripts/s14_feishu_entry.py --text 'S14诊断' --format text
```

A valid generated S14 report must return a report URL under `S14_PUBLIC_BASE_URL` and must not point to demo filenames. Selecting a data source alone does not mean a report was generated.

Shared course Q&A follows `hotel-shared-knowledge`; it does not run these report checks or require a report URL. A knowledge answer must have retrieved sources and pass the final knowledge output command before it is sent.
