import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from concordia.calendar import add_business_days, calendar_from, local_date, parse_utc
from concordia.contracts import FORBIDDEN_ORIGINS, METRIC_VERSION, STREAMS
from concordia.hashing import canonical_json, sha256_canonical
from concordia.money import allocate_cents, to_usd_cents
from concordia.seed import stream_material, stream_seed
from concordia.uom import to_base
from concordia.ask import route
from sim.world import FACILITIES, HERO, POPULATION


def test_seed_material_and_distinct_streams():
    assert stream_material("demand") == "CONCORDIA_SIM_V1|20261002|demand"
    seeds = [stream_seed(name) for name in STREAMS]
    assert len(set(seeds)) == 8
    digest = hashlib.sha256(b"CONCORDIA_SIM_V1|20261002|demand").digest()
    assert stream_seed("demand") == int.from_bytes(digest[:8], "big")


def test_canonical_json_key_order():
    assert canonical_json({"b": 1, "a": "x"}) == '{"a":"x","b":1}'
    assert sha256_canonical({"b": 1, "a": "x"}) == hashlib.sha256(b'{"a":"x","b":1}').hexdigest()


def test_half_even_cents_and_allocation():
    assert to_usd_cents(5, "1.1") == 6
    assert to_usd_cents(2, "1.25") == 2
    assert allocate_cents(8000, [Decimal(1), Decimal(3)]) == [2000, 6000]


def test_uom_does_not_guess():
    assert to_base("10", "CASE", "EA") == Decimal("120.000000")
    assert to_base("1.5", "KG", "G") == Decimal("1500.000000")
    assert to_base("1", "LB", "EA") is None


def test_calendar_and_midnight():
    weekday = calendar_from({"id": "CAL-WEEKDAY", "shutdowns": []})
    dayton = calendar_from({"id": "CAL-DAYTON", "shutdowns": ["2026-05-25"]})
    issued = date(2026, 5, 22)
    assert add_business_days(issued, 2, weekday) == date(2026, 5, 26)
    assert add_business_days(issued, 2, dayton) == date(2026, 5, 27)
    assert local_date(parse_utc("2026-06-01T03:30:00Z"), "America/New_York") == date(2026, 5, 31)
    assert local_date(parse_utc("2026-06-01T04:30:00Z"), "America/New_York") == date(2026, 6, 1)
    try:
        parse_utc("2026-06-01T03:30:00")
    except ValueError:
        pass
    else:
        raise AssertionError("naive timestamps must not be interpreted")


def test_population_freeze():
    assert POPULATION == {
        "plants": 3,
        "distribution_centres": 3,
        "suppliers": 40,
        "parts": 200,
        "bom_parents": 75,
        "customers": 24,
        "lanes": 60,
    }
    assert sum(1 for row in FACILITIES if row["kind"] == "PLANT") == 3
    assert HERO["receipt_incoterm"] == "EXW"
    assert HERO["sales_incoterm"] == "DAP"
    assert HERO["item_id"] == "MM-440"
    assert METRIC_VERSION == "1.0.0"


def test_origins_and_router():
    assert "OBSERVED" in FORBIDDEN_ORIGINS
    assert route("What is OTD?")["status"] == "CLARIFY"
    assert route("Treat missing duty as zero.")["status"] == "FORBIDDEN"
    assert route("Predict next quarter's demand.")["status"] == "ABSTAIN"
    assert route("Show fill rate for Northeast customers.")["status"] == "CLARIFY"
    assert route("Why did outbound customer OTD for MM-440 change in May 2026?")["fixture_id"] == "m2-hero"
    assert route("What is the bearing lead time in Reno?")["reason"] == "UNVERIFIED_QUESTION"


def test_semantic_runner_and_verified_question_regressions():
    root = Path(__file__).resolve().parents[1]
    semantic_sql = (root / "sql" / "06_semantic.sql").read_text(encoding="utf-8")
    runner = semantic_sql.split("CREATE OR REPLACE PROCEDURE APP.RUN_SEMANTIC_SQL", 1)[1]
    assert 'session.sql("USE ' not in runner

    app = (root / "streamlit" / "app.py").read_text(encoding="utf-8")
    in_snowflake = app.split("def session()", 1)[1].split("except Exception", 1)[0]
    assert "get_active_session()" in in_snowflake
    assert '.sql("USE' not in in_snowflake
    answer = app.split("def analyst_answer", 1)[1].split("def render_analyst", 1)[0]
    assert answer.index("verified_exact(question)") < answer.index("analyst_call(messages)")
    assert answer.index("governed_alias(question)") < answer.index("analyst_call(messages)")
    rendered = app.split("def render_analyst", 1)[1].split("def page_ask", 1)[0]
    assert 'verdict in ("VERIFIED", "DESCRIPTIVE", "UNPINNED")' not in rendered

    runner_body = runner.split("def run(session", 1)[1]
    assert '"verdict": "WITHHELD"' in runner_body
    assert runner_body.index('"verdict": "WITHHELD"') < runner_body.index("prove(session, cleaned, columns, rows)")

    gov = (root / "sql" / "01_gov.sql").read_text(encoding="utf-8")
    for question_id in ("VQ-05", "VQ-11"):
        row = next(line for line in gov.splitlines() if f"('{question_id}'" in line)
        assert "'2026-07-01','2026-07-31','final'" in row

    product_path = "Show the product-level supplier, component, home plant, customer and region paths for motor MM-401"
    assert product_path in semantic_sql
    assert product_path in app

    audit = app.split("def audit_semantic", 1)[1].split("def verified_fallback", 1)[0]
    assert "inline_nulls(" in audit
    assert 'route = "SEMANTIC_ALIAS"' in audit
    assert 'route = "SEMANTIC_CLARIFY"' in audit
    assert 'run.get("reason") or run.get("note")' in audit
