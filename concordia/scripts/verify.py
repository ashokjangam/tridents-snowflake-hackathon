"""Verify the deployed SQL metric functions against the golden oracle.

Usage: python scripts/verify.py [golden] [grid] [hero] [ask] [personas] [ontology] [security]
Writes data/generated/verification.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from sf import connect, rows  # noqa: E402

FIELDS = ("status", "numerator", "denominator", "display", "reasons", "coverage", "diagnostic_display", "excluded_count",
          "affected_commitments", "affected_units", "unresolved_records", "evidence_ids")
OUT = ROOT / "data" / "generated" / "verification.json"


HEAD = "%(w)s::VARCHAR, %(ps)s::DATE, %(pe)s::DATE, %(asof)s::TIMESTAMP_TZ, %(item)s::VARCHAR, %(facility)s::VARCHAR"
LINE_SCOPE = HEAD + ", %(geo)s::VARCHAR, %(supplier)s::VARCHAR, %(customer)s::VARCHAR"
FUNCTIONS = {"INBOUND_SUPPLIER_OTD": "COUNT_RESULT_M1", "OUTBOUND_CUSTOMER_OTD": "COUNT_RESULT_M2", "UNIT_FILL_RATE": "FILL_RESULT_M3"}


def result_sql(metric_id: str) -> str:
    if metric_id in FUNCTIONS:
        return f"SELECT * FROM TABLE(CORE.{FUNCTIONS[metric_id]}({LINE_SCOPE}))"
    if metric_id == "DAYS_INVENTORY":
        return ("SELECT * FROM TABLE(CORE.M4_RESULT(%(w)s::VARCHAR, %(asof)s::TIMESTAMP_TZ, %(item)s::VARCHAR, %(facility)s::VARCHAR, "
                "%(klass)s::VARCHAR, %(network)s::BOOLEAN))")
    return f"SELECT * FROM TABLE(CORE.LANDED_RESULT_M5({HEAD}, %(supplier)s::VARCHAR))"


def normalise(row: dict) -> dict:
    out = {}
    for field in FIELDS:
        value = row.get(field.upper())
        if field in ("reasons", "evidence_ids"):
            value = json.loads(value) if isinstance(value, str) else (value or [])
        elif field in ("excluded_count", "affected_commitments", "unresolved_records") and value is not None:
            value = int(value)
        out[field] = value
    return out


def call(cur, metric_id: str, world: str, period, as_of: str, scope: dict) -> dict:
    params = {"w": world, "ps": period[0], "pe": period[1], "asof": as_of, "item": scope.get("item_id"),
              "facility": scope.get("facility_id"), "geo": scope.get("geography_id"), "supplier": scope.get("supplier_id"),
              "customer": scope.get("customer_id"), "klass": scope.get("inventory_class"), "network": bool(scope.get("network"))}
    found = rows(cur, result_sql(metric_id), params)
    return normalise(found[0]) if found else {}


def golden(cur) -> dict:
    from concordia.metrics import run_case
    from eval.fixtures import load_golden, prepare

    checks, failures = 0, []
    for case in load_golden():
        case = prepare(case)
        as_ofs = case["as_of"] if isinstance(case["as_of"], list) else [case["as_of"]]
        for as_of in as_ofs:
            oracle = run_case(case, as_of)
            expected = {field: oracle.get(field) for field in FIELDS}
            actual = call(cur, case["metric_id"], f"EVAL:{case['id']}", case["period"], as_of, case.get("scope") or {})
            checks += 1
            diff = {field: {"sql": actual.get(field), "oracle": expected[field]} for field in FIELDS if actual.get(field) != expected[field]}
            if diff:
                failures.append({"case": case["id"], "as_of": as_of, "diff": diff})
    return {"checks": checks, "failures": failures}


def grid(cur, sample: int = 40) -> dict:
    """Published grid rows must equal a direct call of the result function for the same scope."""
    picked = rows(cur, f"""
        SELECT * FROM APP.V_RESULT_CURRENT
        WHERE METRIC_ID <> 'DAYS_INVENTORY' AND (AS_OF_KIND = 'final' OR PERIOD_START >= '2026-01-01')
        QUALIFY ROW_NUMBER() OVER (PARTITION BY METRIC_ID, STATUS ORDER BY HASH(ITEM_ID, FACILITY_ID, GEOGRAPHY_ID, SUPPLIER_ID,
                                   CUSTOMER_ID, PERIOD_START, AS_OF_KIND)) <= {sample // 5}""")
    hero = rows(cur, "SELECT * FROM APP.V_RESULT_CURRENT WHERE ITEM_ID = 'MM-440' AND PERIOD_START = '2026-05-01'")
    checks, failures = 0, []
    for row in picked + hero:
        scope = {"item_id": row["ITEM_ID"], "facility_id": row["FACILITY_ID"], "geography_id": row["GEOGRAPHY_ID"],
                 "supplier_id": row["SUPPLIER_ID"], "customer_id": row["CUSTOMER_ID"], "inventory_class": row["INVENTORY_CLASS"],
                 "network": row["NETWORK"]}
        as_of = row["AS_OF"].strftime("%Y-%m-%dT%H:%M:%SZ")
        period = (str(row["PERIOD_START"]), str(row["PERIOD_END"]))
        actual = call(cur, row["METRIC_ID"], "MERIDIAN", period, as_of, scope)
        published = normalise(row)
        checks += 1
        diff = {f: {"published": published[f], "function": actual.get(f)} for f in FIELDS if published[f] != actual.get(f)}
        if diff:
            failures.append({"metric": row["METRIC_ID"], "scope": {k: v for k, v in scope.items() if v}, "period": period, "as_of": as_of, "diff": diff})
    return {"checks": checks, "failures": failures}


def hero(cur) -> dict:
    spec = json.loads((ROOT / "data" / "fixtures" / "hero_world_v1.json").read_text(encoding="utf-8"))
    batch2 = rows(cur, "SELECT COUNT(*) AS N FROM LAND.RAW_RECORD WHERE FILE_NAME LIKE '%_b2.jsonl.gz'")[0]["N"] > 0
    checks, failures, skipped = 0, [], 0
    for check in spec["checks"]:
        if check.get("after_batch") == 2 and not batch2:
            skipped += 1
            continue
        for as_of in check["as_of"]:
            actual = call(cur, check["metric_id"], "MERIDIAN", spec["period"], as_of, check["scope"])
            checks += 1
            diff = {k: {"sql": actual.get(k), "expected": v} for k, v in check["expected"].items() if actual.get(k) != v}
            if diff:
                failures.append({"metric": check["metric_id"], "as_of": as_of, "diff": diff})
    return {"checks": checks, "failures": failures, "skipped_until_batch2": skipped}


def security(cur) -> dict:
    results = {}
    origins = rows(cur, """SELECT 'raw' AS T, ORIGIN FROM LAND.RAW_RECORD GROUP BY 2
                           UNION ALL SELECT 'result', ORIGIN FROM APP.METRIC_RESULT GROUP BY 2
                           UNION ALL SELECT 'evidence', ORIGIN FROM GOV.EVIDENCE GROUP BY 2""")
    results["origins"] = sorted({f"{r['T']}:{r['ORIGIN']}" for r in origins})
    results["observed_absent"] = not any("OBSERVED" == (r["ORIGIN"] or "") for r in origins)
    stage = [r["name"] for r in rows(cur, "LIST @LAND.WORLD_STAGE")]
    results["sim_truth_on_stage"] = any("sim_truth" in name for name in stage)
    cur.execute("USE ROLE CONCORDIA_APP_OWNER")
    cur.execute("USE SECONDARY ROLES NONE")
    cur.execute("USE WAREHOUSE CONCORDIA_APP_WH")
    denied = {}
    for obj in ("CORE.PO_LINE", "LAND.RAW_RECORD", "GOV.EVIDENCE", "APP.METRIC_RESULT", "APP.V_RESULT_CURRENT", "APP.V_RECEIPT_CONTRIBUTION"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM CONCORDIA.{obj}")
            denied[obj] = False
        except Exception:  # noqa: BLE001
            denied[obj] = True
    results["app_owner_denied"] = denied
    masked = rows(cur, """SELECT STATUS, DISPLAY FROM TABLE(CONCORDIA.APP.RESULTS_FOR('PLANNER', 'MM-440', 'FAC-DAYTON', NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR))
                          WHERE METRIC_ID = 'LANDED_COST_PER_ACCEPTED_UNIT'""")
    results["planner_dashboard_cost"] = sorted({(r["STATUS"], r["DISPLAY"]) for r in masked})
    shown = rows(cur, """SELECT COUNT(*) AS N FROM TABLE(CONCORDIA.APP.RESULTS_FOR('PROCUREMENT', 'MM-440', 'FAC-DAYTON', NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR))
                         WHERE METRIC_ID = 'LANDED_COST_PER_ACCEPTED_UNIT' AND STATUS <> 'FORBIDDEN'""")
    results["procurement_dashboard_cost_rows"] = shown[0]["N"]
    planner = json.loads(rows(cur, "CALL CONCORDIA.APP.ASK('PLANNER', 'Landed cost per accepted unit for MM-440 at Dayton in May 2026')")[0]["ASK"])
    executive = json.loads(rows(cur, "CALL CONCORDIA.APP.ASK('EXECUTIVE', 'Landed cost per accepted unit for MM-440 at Dayton in May 2026')")[0]["ASK"])
    results["planner_cost_status"] = (planner.get("envelope") or {}).get("status")
    results["executive_cost_status"] = (executive.get("envelope") or {}).get("status")
    bare = json.loads(rows(cur, "CALL CONCORDIA.APP.ASK('EXECUTIVE', 'What was OTD last month?')")[0]["ASK"])
    results["bare_otd_route"] = bare.get("route")
    otif = json.loads(rows(cur, "CALL CONCORDIA.APP.ASK('EXECUTIVE', 'What is our OTIF?')")[0]["ASK"])
    results["otif_route"] = otif.get("route")
    cur.execute("USE ROLE CONCORDIA_ADMIN")
    cur.execute("USE SECONDARY ROLES ALL")
    cur.execute("USE WAREHOUSE CONCORDIA_WH")
    results["passed"] = (results["observed_absent"] and not results["sim_truth_on_stage"]
                         and all(denied.values()) and results["planner_cost_status"] == "FORBIDDEN"
                         and results["planner_dashboard_cost"] == [("FORBIDDEN", None)] and results["procurement_dashboard_cost_rows"] > 0
                         and results["executive_cost_status"] not in (None, "FORBIDDEN")
                         and results["bare_otd_route"] == "ALIAS_CLARIFY" and results["otif_route"] == "ALIAS_REJECT")
    return results


PERSONA_ROLES = {"PLANNER": False, "PROCUREMENT": True, "LOGISTICS": False, "EXECUTIVE": True}
COST = "LANDED_COST_PER_ACCEPTED_UNIT"


def personas(cur) -> dict:
    """Each persona role reads the semantic layer itself. On the rows every persona may see, governed answers must be
    identical; cost is masked by policy; Logistics (Americas sites only) sees no rows for other sites."""
    entitled = {r["PERSONA"]: json.loads(r["ALLOWED_FACILITIES"]) for r in rows(cur, "SELECT PERSONA, ALLOWED_FACILITIES FROM GOV.ENTITLEMENT")}
    all_sites = [r["FACILITY_ID"] for r in rows(cur, "SELECT FACILITY_ID FROM GOV.FACILITY ORDER BY 1")]
    shared = [s for s in all_sites if all("*" in entitled[p] or s in entitled[p] for p in PERSONA_ROLES)]
    in_shared = "(FACILITY_ID IS NULL OR FACILITY_ID IN (" + ", ".join(f"'{s}'" for s in shared) + "))"
    fingerprint_sql = f"""WITH x AS (SELECT r.*, {in_shared} AS SHARED FROM CONCORDIA.APP.SV_RESULT r),
                          f AS (SELECT METRIC_ID, TO_VARCHAR(HASH_AGG(RESULT_KEY, STATUS, DISPLAY, NUMERATOR, DENOMINATOR, VALUE_NUM)) AS FP
                                FROM x WHERE SHARED GROUP BY METRIC_ID)
                          SELECT x.METRIC_ID, COUNT_IF(SHARED) AS N, COUNT_IF(SHARED AND (VALUE_NUM IS NOT NULL OR DISPLAY IS NOT NULL)) AS VISIBLE,
                                 COUNT_IF(NOT SHARED) AS OTHER_SITE_ROWS, ANY_VALUE(f.FP) AS FINGERPRINT
                          FROM x LEFT JOIN f ON f.METRIC_ID = x.METRIC_ID GROUP BY x.METRIC_ID ORDER BY x.METRIC_ID"""
    record_sql = f"""SELECT 'SV_LINE_OUTCOME' AS T, COUNT_IF(NOT {in_shared}) AS N FROM CONCORDIA.APP.SV_LINE_OUTCOME
                     UNION ALL SELECT 'SV_SO_LINE', COUNT_IF(NOT {in_shared}) FROM CONCORDIA.APP.SV_SO_LINE
                     UNION ALL SELECT 'SV_RECEIPT', COUNT_IF(NOT {in_shared}) FROM CONCORDIA.APP.SV_RECEIPT"""
    semantic_sql = """SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY
                        METRICS results.supplier_on_time_delivery, results.customer_on_time_delivery, results.unit_fill_rate,
                                results.landed_cost_per_unit
                        DIMENSIONS results.metric_id, results.governed_value_text
                        WHERE results.scope_level = 'PART_SITE' AND results.known_as_of = 'final' AND results.month = '2026-05-01'
                          AND parts.part_id = 'MM-440' AND sites.site_id = 'FAC-DAYTON') ORDER BY metric_id"""
    by_role, hero, records = {}, {}, {}
    for persona in PERSONA_ROLES:
        with connect(role=f"CONCORDIA_{persona}", warehouse="CONCORDIA_APP_WH") as conn:
            c = conn.cursor()
            c.execute("USE SECONDARY ROLES NONE")
            by_role[persona] = {r["METRIC_ID"]: r for r in rows(c, fingerprint_sql)}
            hero[persona] = {r["METRIC_ID"]: r["GOVERNED_VALUE_TEXT"] for r in rows(c, semantic_sql)}
            records[persona] = {r["T"]: r["N"] for r in rows(c, record_sql)}
    restricted = [p for p in PERSONA_ROLES if "*" not in entitled[p]]
    site_rule = {p: {"other_site_results": sum(m["OTHER_SITE_ROWS"] for m in by_role[p].values()), "other_site_records": records[p]}
                 for p in PERSONA_ROLES}
    site_ok = bool(restricted) and all(
        (site_rule[p]["other_site_results"] == 0 and not any(records[p].values())) if p in restricted
        else (site_rule[p]["other_site_results"] > 0 and all(records[p].values()))
        for p in PERSONA_ROLES)
    metrics = sorted(by_role["PLANNER"])
    checks = {}
    for metric in metrics:
        prints = {p: by_role[p][metric]["FINGERPRINT"] for p in PERSONA_ROLES}
        if metric != COST:
            checks[metric] = {"identical_across_roles": len(set(prints.values())) == 1, "rows": by_role["PLANNER"][metric]["N"],
                              "fingerprint": prints["PLANNER"]}
            continue
        readers = {p for p, cost in PERSONA_ROLES.items() if cost}
        checks[metric] = {"identical_across_cost_readers": len({prints[p] for p in readers}) == 1,
                          "visible_rows_by_role": {p: by_role[p][metric]["VISIBLE"] for p in PERSONA_ROLES},
                          "masked_for_non_readers": all(by_role[p][metric]["VISIBLE"] == 0 for p in PERSONA_ROLES if p not in readers),
                          "visible_for_readers": all(by_role[p][metric]["VISIBLE"] > 0 for p in readers)}
    app_sql = """SELECT METRIC_ID, TO_VARCHAR(HASH_AGG(METRIC_ID, AS_OF_KIND, PERIOD_START, STATUS, DISPLAY, NUMERATOR, DENOMINATOR)) AS F
                 FROM TABLE(CONCORDIA.APP.RESULTS_FOR(%s, %s::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR))
                 WHERE METRIC_ID <> 'LANDED_COST_PER_ACCEPTED_UNIT' GROUP BY 1 ORDER BY 1"""
    cur.execute("USE ROLE CONCORDIA_APP_OWNER")
    cur.execute("USE SECONDARY ROLES NONE")
    cur.execute("USE WAREHOUSE CONCORDIA_APP_WH")
    app = {}
    for item in (None, "MM-440", "CP-1019"):
        prints = {p: tuple((r["METRIC_ID"], r["F"]) for r in rows(cur, app_sql, (p, item))) for p in PERSONA_ROLES}
        app[item or "NETWORK"] = len(set(prints.values())) == 1
    same_question = {}
    question = "Outbound customer OTD for MM-440 in the Northeast in May 2026"
    for persona in ("PLANNER", "PROCUREMENT", "LOGISTICS"):
        result = json.loads(rows(cur, "CALL CONCORDIA.APP.ASK(%s, %s)", (persona, question))[0]["ASK"])
        env = result.get("envelope") or {}
        same_question[persona] = {
            "metric_id": env.get("metric_id"), "status": env.get("status"), "numerator": env.get("numerator"),
            "denominator": env.get("denominator"), "display": env.get("display"), "scope": env.get("scope"),
        }
    same_question_identical = len({json.dumps(value, sort_keys=True) for value in same_question.values()}) == 1
    site_sql = """SELECT COUNT(*) AS N, COUNT_IF(STATUS = 'FORBIDDEN' AND ARRAY_CONTAINS('SITE_NOT_ENTITLED'::VARIANT, REASONS)) AS BLOCKED
                  FROM TABLE(CONCORDIA.APP.RESULTS_FOR(%s, NULL::VARCHAR, 'FAC-STUTTGART', NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR))"""
    app_site = {p: rows(cur, site_sql, (p,))[0] for p in PERSONA_ROLES}
    app_site_ok = all((app_site[p]["BLOCKED"] == app_site[p]["N"] > 0) if p in restricted else (app_site[p]["BLOCKED"] == 0 < app_site[p]["N"])
                      for p in PERSONA_ROLES)
    stuttgart = json.loads(rows(cur, "CALL CONCORDIA.APP.ASK('LOGISTICS', 'Inbound supplier OTD at Stuttgart in May 2026')")[0]["ASK"])
    stuttgart_env = stuttgart.get("envelope") or {}
    ask_site_ok = stuttgart_env.get("status") == "FORBIDDEN" and "SITE_NOT_ENTITLED" in (stuttgart_env.get("reasons") or [])
    cur.execute("USE ROLE CONCORDIA_ADMIN")
    cur.execute("USE SECONDARY ROLES ALL")
    cur.execute("USE WAREHOUSE CONCORDIA_WH")
    passed = (all(v.get("identical_across_roles", True) for v in checks.values())
              and checks.get(COST, {}).get("masked_for_non_readers") and checks.get(COST, {}).get("visible_for_readers")
              and checks.get(COST, {}).get("identical_across_cost_readers") and all(app.values()) and same_question_identical
              and site_ok and app_site_ok and ask_site_ok)
    checked_at = rows(cur, "SELECT CURRENT_TIMESTAMP()::TIMESTAMP_TZ AS T")[0]["T"]
    for persona in PERSONA_ROLES:
        for metric, found in by_role[persona].items():
            cur.execute("""INSERT INTO GOV.PERSONA_CHECK SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s""",
                        (checked_at, persona, f"CONCORDIA_{persona}", metric, found["N"], found["VISIBLE"], found["OTHER_SITE_ROWS"],
                         found["FINGERPRINT"], found["FINGERPRINT"] == by_role["PLANNER"][metric]["FINGERPRINT"], bool(passed)))
    return {"shared_sites": shared, "semantic_layer_by_role": checks, "site_entitlement": site_rule, "site_entitlement_ok": site_ok,
            "app_stuttgart_rows": app_site, "app_site_ok": app_site_ok,
            "logistics_stuttgart_ask": {"status": stuttgart_env.get("status"), "reasons": stuttgart_env.get("reasons")},
            "app_dashboard_identical": app, "same_question_by_persona": same_question,
            "same_question_identical": same_question_identical, "hero_by_role": hero, "passed": bool(passed)}


def ontology(cur) -> dict:
    """Prove that advertised ontology relationships, IoT, lots and primary semantic questions exist and execute."""
    edge_rows = rows(cur, """SELECT EDGE_TYPE, COUNT(*) AS N FROM CORE.KG_EDGE
                             WHERE EDGE_TYPE IN ('SUBSTITUTES_FOR','CONSUMES','PARENT_OF','BELONGS_TO_FAMILY',
                                                 'IN_COUNTRY','IN_REGION','CONTAINS','SENSES','ALLOCATED_TO')
                             GROUP BY EDGE_TYPE ORDER BY EDGE_TYPE""")
    edges = {r["EDGE_TYPE"]: r["N"] for r in edge_rows}
    counts = rows(cur, """SELECT
      (SELECT COUNT(*) FROM CORE.IOT_EVENT) AS IOT_EVENTS,
      (SELECT COUNT(DISTINCT LOT_ID) FROM CORE.LOT_TRACE) AS LOTS,
      (SELECT COUNT(DISTINCT ITEM_ID) FROM APP.SV_RESULT WHERE METRIC_ID = 'DAYS_INVENTORY') AS INVENTORY_PARTS,
      (SELECT COUNT(*) FROM APP.ANALYST_VERIFIED) AS VERIFIED_QUERIES,
      (SELECT COUNT(*) FROM GOV.VERIFIED_QUESTION WHERE ANALYST_SQL IS NULL) AS CATALOG_WITHOUT_SQL""")[0]
    unpinned = rows(cur, """SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY
                              METRICS results.days_of_inventory, results.governed_answer_count)""")[0]
    lines = rows(cur, """SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY
                           METRICS line_outcomes.counted_lines, line_outcomes.on_time_lines, line_outcomes.missed_lines
                           WHERE line_outcomes.metric_id = 'OUTBOUND_CUSTOMER_OTD' AND line_outcomes.known_as_of = 'final'
                             AND line_outcomes.month = '2026-05-01' AND parts.part_id = 'MM-440' AND regions.region_id = 'GEO-NORTHEAST')""")[0]
    published = rows(cur, """SELECT NUMERATOR, DENOMINATOR FROM APP.SV_RESULT WHERE METRIC_ID = 'OUTBOUND_CUSTOMER_OTD' AND AS_OF_KIND = 'final'
                               AND PERIOD_START = '2026-05-01' AND SCOPE_LEVEL = 'PART_REGION' AND ITEM_ID = 'MM-440'
                               AND GEOGRAPHY_ID = 'GEO-NORTHEAST'""")[0]
    line_parity = {"on_time_lines": int(lines["ON_TIME_LINES"]), "counted_lines": int(lines["COUNTED_LINES"]),
                   "missed_lines": int(lines["MISSED_LINES"]), "published_numerator": published["NUMERATOR"],
                   "published_denominator": published["DENOMINATOR"]}
    line_parity["matched"] = (str(line_parity["on_time_lines"]) == str(published["NUMERATOR"])
                              and str(line_parity["counted_lines"]) == str(published["DENOMINATOR"]))
    single_row = {"unfiltered_days_of_inventory": unpinned["DAYS_OF_INVENTORY"], "answers_matched": unpinned["GOVERNED_ANSWER_COUNT"],
                  "null_when_not_one_answer": unpinned["DAYS_OF_INVENTORY"] is None and unpinned["GOVERNED_ANSWER_COUNT"] > 1}
    scopes = rows(cur, """SELECT ITEM_ID, FACILITY_ID, NETWORK
                          FROM TABLE(CORE.M4_GRID('MERIDIAN', '2026-07-15 23:59:59+00'::TIMESTAMP_TZ, 'FINISHED_GOODS'))
                          QUALIFY ROW_NUMBER() OVER (PARTITION BY NETWORK ORDER BY ITEM_ID, FACILITY_ID) <= 3""")
    m4_parity = []
    for as_of in ("2026-06-05 23:59:59+00", "2026-07-15 23:59:59+00"):
        for scope in scopes:
            comparison = rows(cur, """WITH g AS (
                SELECT * FROM TABLE(CORE.M4_GRID('MERIDIAN', %s::TIMESTAMP_TZ, 'FINISHED_GOODS'))
                WHERE ITEM_ID = %s AND EQUAL_NULL(FACILITY_ID, %s) AND NETWORK = %s
              ), r AS (
                SELECT * FROM TABLE(CORE.M4_RESULT(
                  'MERIDIAN', %s::TIMESTAMP_TZ, %s::VARCHAR, %s::VARCHAR, 'FINISHED_GOODS', %s))
              )
              SELECT COUNT(*) = 1
                 AND BOOLOR_AGG(g.STATUS = r.STATUS
                   AND EQUAL_NULL(g.NUMERATOR, r.NUMERATOR)
                   AND EQUAL_NULL(g.DENOMINATOR, r.DENOMINATOR)
                   AND EQUAL_NULL(g.DISPLAY, r.DISPLAY)
                   AND EQUAL_NULL(g.VALUE_NUM, r.VALUE_NUM)
                   AND EQUAL_NULL(TO_JSON(g.REASONS), TO_JSON(r.REASONS))) AS MATCHED
              FROM g FULL OUTER JOIN r ON TRUE""",
                (as_of, scope["ITEM_ID"], scope["FACILITY_ID"], scope["NETWORK"],
                 as_of, scope["ITEM_ID"], scope["FACILITY_ID"], scope["NETWORK"]))[0]
            m4_parity.append({"as_of": as_of, **scope, "matched": bool(comparison["MATCHED"])})
    cur.execute("USE ROLE CONCORDIA_APP_OWNER")
    cur.execute("USE SECONDARY ROLES NONE")
    cur.execute("USE WAREHOUSE CONCORDIA_APP_WH")
    approved = rows(cur, """SELECT QUESTION, SQL_TEXT FROM CONCORDIA.APP.ANALYST_VERIFIED ORDER BY QUESTION""")
    executions = []
    for item in approved:
        result = json.loads(rows(cur, "CALL CONCORDIA.APP.RUN_SEMANTIC_SQL('EXECUTIVE', %s)", (item["SQL_TEXT"],))[0]["RUN_SEMANTIC_SQL"])
        executions.append({"question": item["QUESTION"], "verdict": result.get("verdict"), "rows": result.get("row_count"),
                           "columns": result.get("columns")})
    cost_sql = next(item["SQL_TEXT"] for item in approved
                    if item["QUESTION"] == "Compare landed cost for MM-440 at Dayton in May 2026 between 5 June and 15 July")
    masked_cost = json.loads(rows(cur, "CALL CONCORDIA.APP.RUN_SEMANTIC_SQL('PLANNER', %s)", (cost_sql,))[0]["RUN_SEMANTIC_SQL"])
    comparison = next(item for item in executions if item["question"].startswith("Compare supplier on-time delivery"))
    cur.execute("USE ROLE CONCORDIA_ADMIN")
    cur.execute("USE SECONDARY ROLES ALL")
    cur.execute("USE WAREHOUSE CONCORDIA_WH")
    expected_edges = {"SUBSTITUTES_FOR", "CONSUMES", "PARENT_OF", "BELONGS_TO_FAMILY", "IN_COUNTRY", "IN_REGION", "CONTAINS", "SENSES",
                      "ALLOCATED_TO"}
    passed = (expected_edges <= {name for name, count in edges.items() if count > 0}
              and counts["IOT_EVENTS"] > 0 and counts["LOTS"] > 0 and counts["INVENTORY_PARTS"] >= 40
              and counts["VERIFIED_QUERIES"] >= 21 and counts["CATALOG_WITHOUT_SQL"] == 0
              and len(executions) == counts["VERIFIED_QUERIES"]
              and single_row["null_when_not_one_answer"] and line_parity["matched"]
              and len(m4_parity) >= 8 and all(item["matched"] for item in m4_parity)
              and masked_cost.get("verdict") == "WITHHELD" and not masked_cost.get("rows")
              and "GOVERNED_VALUE" in (comparison.get("columns") or [])
              and all(item["verdict"] in ("VERIFIED", "DESCRIPTIVE") and item["rows"] > 0 for item in executions))
    return {"edge_counts": edges, "counts": counts, "m4_grid_parity": m4_parity, "single_row_rule": single_row,
            "line_outcomes_match_published": line_parity, "semantic_questions": executions,
            "planner_landed_cost": {"verdict": masked_cost.get("verdict"), "rows_returned": len(masked_cost.get("rows") or [])},
            "passed": bool(passed)}


def ask(cur) -> dict:
    out = []
    for question in ("Why did outbound customer OTD for MM-440 change in May 2026?",
                     "Compare landed cost for MM-440 at Dayton in May 2026 between 5 June and 15 July",
                     "How did inbound supplier on-time delivery look at Stuttgart in March 2026?"):
        started = time.time()
        result = json.loads(rows(cur, "CALL APP.ASK('EXECUTIVE', %s)", (question,))[0]["ASK"])
        env = result.get("envelope") or {}
        out.append({"question": question, "route": result.get("route"), "status": env.get("status"), "display": env.get("display"),
                    "narration_source": result.get("narration_source"), "narration": result.get("narration"),
                    "note": result.get("narration_note"), "seconds": round(time.time() - started, 1)})
    return {"answers": out, "passed": all(
        item["route"] not in (None, "ALIAS_REJECT", "ALIAS_CLARIFY")
        and item["status"] == "COMPLETE" and item["display"] is not None
        for item in out)}


def main(argv: list[str]) -> None:
    wanted = argv or ["golden"]
    report = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("USE ROLE CONCORDIA_ADMIN")
        cur.execute("USE WAREHOUSE CONCORDIA_WH")
        cur.execute("USE DATABASE CONCORDIA")
        if "golden" in wanted:
            report["golden"] = golden(cur)
            print(f"golden: {report['golden']['checks']} checks, {len(report['golden']['failures'])} failures")
            for failure in report["golden"]["failures"]:
                print(" ", failure["case"], failure["as_of"], json.dumps(failure["diff"], default=str)[:600])
        for name, fn in (("grid", grid), ("hero", hero)):
            if name in wanted:
                report[name] = fn(cur)
                print(f"{name}: {report[name]['checks']} checks, {len(report[name]['failures'])} failures")
                for failure in report[name]["failures"][:8]:
                    print(" ", json.dumps(failure, default=str)[:700])
        if "ask" in wanted:
            report["ask"] = ask(cur)
            for answer in report["ask"]["answers"]:
                print(" ", json.dumps(answer, default=str)[:900])
        if "personas" in wanted:
            report["personas"] = personas(cur)
            print("personas:", json.dumps(report["personas"], default=str, indent=1))
        if "ontology" in wanted:
            report["ontology"] = ontology(cur)
            print("ontology:", json.dumps(report["ontology"], default=str, indent=1))
        if "security" in wanted:
            report["security"] = security(cur)
            print("security:", json.dumps(report["security"], default=str))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    failed = []
    for name in wanted:
        section = report.get(name, {})
        if section.get("failures") or section.get("passed") is False:
            failed.append(name)
    if failed:
        raise SystemExit("Verification failed: " + ", ".join(failed))


if __name__ == "__main__":
    main(sys.argv[1:])
