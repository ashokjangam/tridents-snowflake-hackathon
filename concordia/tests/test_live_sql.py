"""Run the deployed Snowflake SQL against the golden oracle and the governance rules.

Opt in with CONCORDIA_LIVE=1 and a Snowflake connection in ~/.snowflake/connections.toml; otherwise every test skips.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIVE = os.environ.get("CONCORDIA_LIVE") == "1"
HAVE_CONNECTOR = importlib.util.find_spec("snowflake.connector") is not None if importlib.util.find_spec("snowflake") else False
HAVE_CONFIG = (Path.home() / ".snowflake" / "connections.toml").exists()

pytestmark = [pytest.mark.live, pytest.mark.skipif(not (LIVE and HAVE_CONNECTOR and HAVE_CONFIG),
                                                   reason="set CONCORDIA_LIVE=1 with a Snowflake connection to run live SQL tests")]


@pytest.fixture(scope="module")
def cur():
    sys.path.insert(0, str(ROOT / "scripts"))
    from sf import connect

    with connect() as conn:
        c = conn.cursor()
        c.execute("USE ROLE CONCORDIA_ADMIN")
        c.execute("USE SECONDARY ROLES ALL")
        c.execute("USE WAREHOUSE CONCORDIA_WH")
        c.execute("USE DATABASE CONCORDIA")
        yield c


@pytest.fixture(scope="module")
def verify():
    sys.path.insert(0, str(ROOT / "scripts"))
    import verify as module

    return module


def test_sql_metric_functions_equal_python_oracle(cur, verify):
    report = verify.golden(cur)
    assert report["checks"] > 0
    assert report["failures"] == []


def test_hero_world_expectations(cur, verify):
    report = verify.hero(cur)
    assert report["checks"] > 0
    assert report["failures"] == []


def test_published_grid_equals_result_functions(cur, verify):
    report = verify.grid(cur, sample=20)
    assert report["failures"] == []


def test_semantic_metric_is_null_unless_one_answer_matches(cur):
    from sf import rows

    found = rows(cur, "SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY "
                      "METRICS results.days_of_inventory, results.governed_answer_count)")[0]
    assert found["DAYS_OF_INVENTORY"] is None and found["GOVERNED_ANSWER_COUNT"] > 1


def test_one_verified_question_catalog(cur):
    from sf import rows

    sys.path.insert(0, str(ROOT / "scripts"))
    from catalog import verified_queries

    mirrored = {qid: question for qid, question, _ in verified_queries((ROOT / "sql" / "06_semantic.sql").read_text(encoding="utf-8"))}
    catalog = {r["QUESTION_ID"]: r["QUESTION"] for r in rows(cur, "SELECT QUESTION_ID, QUESTION FROM GOV.VERIFIED_QUESTION")}
    assert mirrored == catalog
    assert rows(cur, "SELECT COUNT(*) AS N FROM GOV.VERIFIED_QUESTION WHERE ANALYST_SQL IS NULL")[0]["N"] == 0


def test_line_outcomes_add_up_to_the_published_answer(cur):
    from sf import rows

    lines = rows(cur, """SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY
                           METRICS line_outcomes.counted_lines, line_outcomes.on_time_lines
                           WHERE line_outcomes.metric_id = 'OUTBOUND_CUSTOMER_OTD' AND line_outcomes.known_as_of = 'final'
                             AND line_outcomes.month = '2026-05-01' AND parts.part_id = 'MM-440' AND regions.region_id = 'GEO-NORTHEAST')""")[0]
    published = rows(cur, """SELECT NUMERATOR, DENOMINATOR FROM APP.SV_RESULT WHERE METRIC_ID = 'OUTBOUND_CUSTOMER_OTD'
                               AND AS_OF_KIND = 'final' AND PERIOD_START = '2026-05-01' AND SCOPE_LEVEL = 'PART_REGION'
                               AND ITEM_ID = 'MM-440' AND GEOGRAPHY_ID = 'GEO-NORTHEAST'""")[0]
    assert str(int(lines["ON_TIME_LINES"])) == published["NUMERATOR"]
    assert str(int(lines["COUNTED_LINES"])) == published["DENOMINATOR"]


def test_logistics_role_sees_only_entitled_sites():
    sys.path.insert(0, str(ROOT / "scripts"))
    from sf import connect, rows

    with connect(role="CONCORDIA_LOGISTICS", warehouse="CONCORDIA_APP_WH") as conn:
        c = conn.cursor()
        c.execute("USE SECONDARY ROLES NONE")
        sites = {r["FACILITY_ID"] for r in rows(c, "SELECT DISTINCT FACILITY_ID FROM CONCORDIA.APP.SV_RESULT WHERE FACILITY_ID IS NOT NULL")}
        network = rows(c, "SELECT COUNT(*) AS N FROM CONCORDIA.APP.SV_RESULT WHERE FACILITY_ID IS NULL")[0]["N"]
    assert sites and sites <= {"FAC-DAYTON", "FAC-RENO", "DC-NEWARK", "DC-OAKLAND"}
    assert network > 0
