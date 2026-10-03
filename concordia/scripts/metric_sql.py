"""Shared SQL aggregate expressions for metric contract 1.0.0.

The same text is substituted into the CORE.*_RESULT functions (ad hoc answers) and
APP.PUBLISH_RESULTS (the published grid), so both paths aggregate identically.
"""

STRUCTURAL = "ARRAY_CONSTRUCT('INCOTERM_MISSING','INCOTERM_UNSUPPORTED','TIMEZONE_MISSING','CALENDAR_MISSING')"

E = "COALESCE(COUNT_IF(OUTCOME IN ('HIT','MISS')), 0)"
H = "COALESCE(COUNT_IF(OUTCOME = 'HIT'), 0)"
X = "COALESCE(COUNT_IF(OUTCOME = 'EXCLUDED'), 0)"
MISSES = "COALESCE(COUNT_IF(OUTCOME = 'MISS'), 0)"
S = f"COALESCE(BOOLOR_AGG(ARRAYS_OVERLAP(REASONS, {STRUCTURAL})), FALSE)"


def _d4(expr: str) -> str:
    return f"TO_VARCHAR(ROUND({expr}, 4, 'HALF_TO_EVEN')::NUMBER(38,4))"


def _q6(expr: str) -> str:
    return f"TO_VARCHAR(({expr})::NUMBER(38,6))"


def _r6(expr: str) -> str:
    return f"TO_VARCHAR(ROUND({expr}, 6, 'HALF_TO_EVEN')::NUMBER(38,6))"


COUNT_AGG = ",\n       ".join([
    f"CASE WHEN {E} = 0 AND {S} THEN 'ABSTAIN' WHEN {E} = 0 THEN 'ZERO_DENOMINATOR' WHEN {S} THEN 'INCOMPLETE' ELSE 'COMPLETE' END",
    f"IFF({E} = 0, NULL, TO_VARCHAR({H}))",
    f"IFF({E} = 0, NULL, TO_VARCHAR({E}))",
    f"IFF({E} = 0, NULL, {_d4(f'{H}::NUMBER(38,12) / {E}')})",
    f"IFF({E} = 0, NULL, ({H}::NUMBER(38,12) / {E})::NUMBER(38,12))",
    "COALESCE(ARRAY_SORT(ARRAY_UNION_AGG(REASONS)), ARRAY_CONSTRUCT())",
    f"IFF({E} = 0, NULL, {_r6(f'{E}::NUMBER(38,12) / ({E} + {X})')})",
    "NULL::VARCHAR",
    X,
    MISSES,
    _q6("COALESCE(SUM(IFF(OUTCOME = 'MISS', QTY, 0)), 0)"),
    X,
    "COALESCE(ARRAY_AGG(LINE_ID) WITHIN GROUP (ORDER BY LINE_ID), ARRAY_CONSTRUCT())",
])

I = "COALESCE(COUNT_IF(OUTCOME <> 'EXCLUDED'), 0)"
N = "COALESCE(SUM(IFF(OUTCOME <> 'EXCLUDED', FILLED_QTY, 0)), 0)"
DEN = "COALESCE(SUM(IFF(OUTCOME <> 'EXCLUDED', QTY, 0)), 0)"

FILL_AGG = ",\n       ".join([
    f"IFF({DEN} > 0, 'COMPLETE', 'ZERO_DENOMINATOR')",
    f"IFF({DEN} > 0, {_q6(N)}, NULL)",
    f"IFF({DEN} > 0, {_q6(DEN)}, NULL)",
    f"IFF({DEN} > 0, {_d4(f'{N}::NUMBER(38,12) / NULLIF({DEN}, 0)')}, NULL)",
    f"IFF({DEN} > 0, ({N}::NUMBER(38,12) / NULLIF({DEN}, 0))::NUMBER(38,12), NULL)",
    "COALESCE(ARRAY_SORT(ARRAY_UNION_AGG(REASONS)), ARRAY_CONSTRUCT())",
    f"IFF({DEN} > 0, {_r6(f'{I}::NUMBER(38,12) / ({I} + {X})')}, NULL)",
    "NULL::VARCHAR",
    X,
    MISSES,
    _q6("COALESCE(SUM(IFF(OUTCOME = 'MISS', QTY, 0)), 0)"),
    X,
    "COALESCE(ARRAY_AGG(LINE_ID) WITHIN GROUP (ORDER BY LINE_ID), ARRAY_CONSTRUCT())",
])

T = "COALESCE(SUM(ACCEPTED_QTY), 0)"
CQ = "COALESCE(SUM(IFF(COVERED, ACCEPTED_QTY, 0)), 0)"
CC = "COALESCE(SUM(IFF(COVERED, CENTS, 0)), 0)"
U = "COALESCE(COUNT_IF(NOT COVERED), 0)"
OK = f"({T} > 0 AND {U} = 0)"

LANDED_AGG = ",\n       ".join([
    f"CASE WHEN {T} = 0 THEN 'ZERO_DENOMINATOR' WHEN {U} > 0 THEN 'INCOMPLETE' ELSE 'COMPLETE' END",
    f"IFF({OK}, TO_VARCHAR({CC}), NULL)",
    f"IFF({OK}, {_q6(CQ)}, NULL)",
    f"IFF({OK}, {_d4(f'{CC}::NUMBER(38,12) / NULLIF({CQ} * 100, 0)')}, NULL)",
    f"IFF({OK}, ({CC}::NUMBER(38,12) / NULLIF({CQ} * 100, 0))::NUMBER(38,12), NULL)",
    "COALESCE(ARRAY_SORT(ARRAY_UNION_AGG(GAPS)), ARRAY_CONSTRUCT())",
    f"IFF({T} > 0, {_r6(f'{CQ}::NUMBER(38,12) / NULLIF({T}, 0)')}, NULL)",
    f"IFF({T} > 0 AND {U} > 0 AND {CQ} > 0, {_d4(f'{CC}::NUMBER(38,12) / NULLIF({CQ} * 100, 0)')}, NULL)",
    U,
    "0",
    "'0.000000'",
    U,
    "COALESCE(ARRAY_AGG(RECEIPT_ID) WITHIN GROUP (ORDER BY RECEIPT_ID), ARRAY_CONSTRUCT())",
])

RESULT_COLUMNS = ("STATUS", "NUMERATOR", "DENOMINATOR", "DISPLAY", "VALUE_NUM", "REASONS", "COVERAGE", "DIAGNOSTIC_DISPLAY",
                  "EXCLUDED_COUNT", "AFFECTED_COMMITMENTS", "AFFECTED_UNITS", "UNRESOLVED_RECORDS", "EVIDENCE_IDS")


def named(agg: str) -> str:
    parts = agg.split(",\n       ")
    return ",\n       ".join(f"{expr} AS {name}" for expr, name in zip(parts, RESULT_COLUMNS))


REPLACEMENTS = {"{{COUNT_AGG}}": COUNT_AGG, "{{FILL_AGG}}": FILL_AGG, "{{LANDED_AGG}}": LANDED_AGG,
                "{{COUNT_AGG_NAMED}}": named(COUNT_AGG), "{{FILL_AGG_NAMED}}": named(FILL_AGG), "{{LANDED_AGG_NAMED}}": named(LANDED_AGG)}
