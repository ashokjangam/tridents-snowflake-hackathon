"""Deploy Concordia to the configured Snowflake account.

Usage: python scripts/deploy.py [step ...]
Steps: bootstrap gov land core metrics app eval semantic streamlit load1 load2 resolve publish all
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from metric_sql import REPLACEMENTS  # noqa: E402
from sf import connect, rows, run_file  # noqa: E402

SQL = ROOT / "sql"
WORLD = ROOT / "data" / "generated" / "world"
NARRATION_MODEL = "llama3.1-70b"
ORDER = ["bootstrap", "gov", "land", "core", "metrics", "app", "upload", "load1", "resolve", "eval", "publish", "personas", "semantic", "streamlit", "load2"]


def put(cur, local: Path, target: str) -> None:
    uri = local.resolve().as_posix()
    cur.execute(f"PUT 'file://{uri}' @{target} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")


def step_bootstrap(cur):
    cur.execute("USE ROLE ACCOUNTADMIN")
    cur.execute("SET CONCORDIA_USER = CURRENT_USER()")
    run_file(cur, SQL / "00_setup.sql")


def admin(cur):
    cur.execute("USE ROLE CONCORDIA_ADMIN")
    cur.execute("USE WAREHOUSE CONCORDIA_WH")
    cur.execute("USE DATABASE CONCORDIA")


def step_gov(cur):
    run_file(cur, SQL / "01_gov.sql", {"__NARRATION_MODEL__": NARRATION_MODEL})
    # 01_gov.sql recreates the master tables empty; on a redeploy they must be refilled or every live answer abstains.
    try:
        staged = rows(cur, "LIST @LAND.WORLD_STAGE PATTERN='.*governance[.]json'")
    except Exception:
        staged = []
    if staged:
        print("  governance:", rows(cur, "CALL LAND.LOAD_GOVERNANCE()"))


def step_land(cur):
    run_file(cur, SQL / "02_land.sql")


def step_core(cur):
    run_file(cur, SQL / "03_core.sql")


def step_metrics(cur):
    run_file(cur, SQL / "04_metrics.sql", REPLACEMENTS, echo=False)


def step_app(cur):
    run_file(cur, SQL / "05_app.sql", {**REPLACEMENTS, "__NARRATION_MODEL__": NARRATION_MODEL}, echo=False)


def step_reset(cur):
    """Clear landed extracts so a regenerated world reloads cleanly. Audit tables are append-only and kept."""
    admin(cur)
    cur.execute("REMOVE @LAND.WORLD_STAGE/sources")
    for table in ("LAND.RAW_RECORD", "LAND.QUARANTINE", "APP.PUBLISH_RUN", "APP.METRIC_RESULT", "APP.METRIC_CONTRIBUTION",
                  "APP.RECEIPT_CONTRIBUTION"):
        cur.execute(f"TRUNCATE TABLE IF EXISTS {table}")
    cur.execute("CREATE OR REPLACE STREAM LAND.RAW_RECORD_STREAM ON TABLE LAND.RAW_RECORD APPEND_ONLY = TRUE")
    cur.execute("GRANT SELECT ON STREAM LAND.RAW_RECORD_STREAM TO ROLE CONCORDIA_TRANSFORM")


def step_upload(cur):
    admin(cur)
    put(cur, WORLD / "governance.json", "LAND.WORLD_STAGE")
    put(cur, WORLD / "manifest.json", "LAND.WORLD_STAGE")
    for path in sorted((WORLD / "sources").glob("*.jsonl.gz")):
        put(cur, path, "LAND.WORLD_STAGE/sources")
    print("  governance:", rows(cur, "CALL LAND.LOAD_GOVERNANCE()"))


def step_load1(cur):
    admin(cur)
    print("  batch 1:", rows(cur, "CALL LAND.LOAD_EXTRACTS('.*_b1[.]jsonl[.]gz')"))


def step_load2(cur):
    admin(cur)
    print("  batch 2:", rows(cur, "CALL LAND.LOAD_EXTRACTS('.*_b2[.]jsonl[.]gz')"))


def step_resolve(cur):
    admin(cur)
    started = time.time()
    print("  resolve:", rows(cur, "CALL CORE.RESOLVE()"), f"{time.time() - started:.1f}s")


def step_eval(cur):
    admin(cur)
    from eval.fixtures import load_golden, prepare

    cases = [prepare(case) for case in load_golden()]
    path = WORLD / "eval_cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    put(cur, path, "LAND.WORLD_STAGE")
    run_file(cur, SQL / "08_eval.sql", echo=False)
    print("  eval:", rows(cur, "CALL CORE.LOAD_EVAL_WORLDS()"))


def step_publish(cur):
    admin(cur)
    started = time.time()
    print("  publish:", rows(cur, "CALL APP.PUBLISH_RESULTS()"), f"{time.time() - started:.1f}s")


def step_personas(cur):
    cur.execute("USE ROLE ACCOUNTADMIN")
    cur.execute("SET CONCORDIA_USER = CURRENT_USER()")
    run_file(cur, SQL / "09_personas.sql")


def step_semantic(cur):
    admin(cur)
    run_file(cur, SQL / "06_semantic.sql", echo=False)
    text = (SQL / "06_semantic.sql").read_text(encoding="utf-8")
    pairs = re.findall(r"QUESTION '([^']+)'.*?SQL\s+'((?:[^']|'')*)'", text, flags=re.S)
    cur.execute("CREATE OR REPLACE TABLE CONCORDIA.APP.ANALYST_VERIFIED (QUESTION VARCHAR, SQL_TEXT VARCHAR)")
    for question, statement in pairs:
        cur.execute("INSERT INTO CONCORDIA.APP.ANALYST_VERIFIED (QUESTION, SQL_TEXT) VALUES (%s, %s)",
                    (question, statement.replace("''", "'")))
    cur.execute("GRANT SELECT ON TABLE CONCORDIA.APP.ANALYST_VERIFIED TO ROLE CONCORDIA_APP_OWNER")
    print(f"  verified queries: {len(pairs)}")


def step_streamlit(cur):
    cur.execute("USE ROLE CONCORDIA_APP_OWNER")
    cur.execute("USE SECONDARY ROLES NONE")
    cur.execute("CREATE STAGE IF NOT EXISTS CONCORDIA.APP.STREAMLIT_STAGE DIRECTORY = (ENABLE = TRUE)")
    for path in sorted((ROOT / "streamlit").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".yml", ".toml", ".svg", ".png", ".css"}:
            rel = path.relative_to(ROOT / "streamlit").parent.as_posix()
            target = "CONCORDIA.APP.STREAMLIT_STAGE" + ("" if rel == "." else "/" + rel)
            put(cur, path, target)
    for name in ("concordia-logo.svg", "concordia-icon.svg", "concordia-logo-reversed.svg"):
        put(cur, ROOT / "assets" / name, "CONCORDIA.APP.STREAMLIT_STAGE/assets")
    run_file(cur, SQL / "07_streamlit.sql", echo=True)
    found = rows(cur, "SHOW STREAMLITS IN SCHEMA CONCORDIA.APP")
    print("  streamlit:", [(r["name"], r["owner"], r["query_warehouse"], r.get("url_id")) for r in found])
    cur.execute("USE SECONDARY ROLES ALL")


STEPS = {name: globals()[f"step_{name}"] for name in ORDER + ["reset"]}


def main(argv: list[str]) -> None:
    wanted = ORDER if not argv or argv == ["all"] else argv
    with connect() as conn:
        cur = conn.cursor()
        for name in wanted:
            print(f"== {name}")
            if name not in ("bootstrap", "streamlit"):
                admin(cur)
            STEPS[name](cur)


if __name__ == "__main__":
    main(sys.argv[1:])
