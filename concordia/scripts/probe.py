"""Read-only account probe."""

from sf import connect, rows

QUERIES = [
    "select current_role() r, current_user() u, current_warehouse() w, current_version() v, current_region() reg",
    "show warehouses",
    "select distinct version from information_schema.packages where language='python' and package_name='streamlit' order by version",
    "show roles like 'CONCORDIA%'",
    "show databases like 'CONCORDIA'",
    "select ai_complete('claude-3-5-sonnet', 'Reply with OK') as r",
    "select ai_complete('mistral-large2', 'Reply with OK') as r",
    "select ai_complete('llama3.1-70b', 'Reply with OK') as r",
    "show parameters like 'CORTEX_ENABLED_CROSS_REGION' in account",
]

con = connect()
cur = con.cursor()
for q in QUERIES:
    try:
        out = rows(cur, q)
        if q.startswith("show warehouses"):
            out = [{k: r[k] for k in ("name", "size", "state", "owner")} for r in out]
        print(q[:70], "->", out[-25:])
    except Exception as exc:  # noqa: BLE001
        print(q[:70], "ERR", str(exc)[:220])
