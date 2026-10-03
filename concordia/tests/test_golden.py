from decimal import Decimal

from concordia.hashing import sha256_canonical
from concordia.metrics import evidence_preimage, run_case
from eval.fixtures import load_golden, prepare


def test_golden_fixtures_match_oracle():
    cases = load_golden()
    assert cases, "the frozen fixture file is empty"
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        assert case["contract"] == "CONCORDIA_SIM_V1"
        prepared = prepare(case)
        for as_of in case["as_of"]:
            actual = run_case(prepared, as_of)
            expected = case["expected"]
            for key, value in expected.items():
                assert actual[key] == value, f"{case['id']} {as_of} {key}: {actual[key]!r} != {value!r}"
            assert actual["origin"] == "DERIVED_FROM_SYNTHETIC"
            assert actual["metric_version"] == "1.0.0"


def test_hero_otd_is_unchanged_when_only_cost_invoices_arrive():
    hero = {case["id"]: case for case in load_golden()}
    early = run_case(prepare(hero["m2-hero"]), "2026-06-05T23:59:59Z")
    final = run_case(prepare(hero["m2-hero"]), "2026-07-15T23:59:59Z")
    assert evidence_preimage(early, hero["m2-hero"])["numerator"] == "1"
    early_payload = evidence_preimage(early, hero["m2-hero"])
    final_payload = evidence_preimage(final, hero["m2-hero"])
    assert early_payload["as_of"] != final_payload["as_of"]
    early_payload["as_of"] = final_payload["as_of"] = None
    assert sha256_canonical(early_payload) == sha256_canonical(final_payload)
    cost_early = run_case(prepare(hero["m5-hero-early"]), "2026-06-05T23:59:59Z")
    cost_final = run_case(prepare(hero["m5-hero-final"]), "2026-07-15T23:59:59Z")
    assert cost_early["status"] == "INCOMPLETE"
    assert cost_early["display"] is None
    assert cost_final["numerator"] == "125000"
    assert Decimal(cost_final["display"]) == Decimal("12.5000")


def test_rating_and_returns_do_not_change_otd():
    case = next(item for item in load_golden() if item["id"] == "m2-hero")
    prepared = prepare(case)
    baseline = run_case(prepared, case["as_of"][0])
    prepared["lines"][0]["rating"] = 5
    prepared["lines"][0]["return_qty"] = "9"
    assert run_case(prepared, case["as_of"][0]) == baseline


def test_evidence_hash_covers_only_contract_fields():
    # Persona sameness is proven live against Snowflake roles by `scripts/verify.py personas`; this only checks the hash input.
    case = next(item for item in load_golden() if item["id"] == "m2-hero")
    result = run_case(prepare(case), case["as_of"][0])
    first = sha256_canonical(evidence_preimage(result, case))
    assert sha256_canonical(evidence_preimage({**result, "viewer": "anyone"}, case)) == first
    assert sha256_canonical(evidence_preimage({**result, "numerator": "2"}, case)) != first
    assert len(first) == 64


def test_demand_window_expands_to_28_days():
    case = next(item for item in load_golden() if item["id"] == "m4-hero-early")
    prepared = prepare(case)
    assert len(prepared["demand"]) == 28


def test_missing_duty_is_not_stored_as_zero():
    case = next(item for item in load_golden() if item["id"] == "m5-missing-duty")
    actual = run_case(prepare(case), case["as_of"][0])
    assert actual["status"] == "INCOMPLETE"
    assert actual["numerator"] is None
    assert "DUTY_AMOUNT_MISSING" in actual["reasons"]
