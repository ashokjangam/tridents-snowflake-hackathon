"""Concordia — governed supply chain intelligence, running in Streamlit in Snowflake.

Every number on screen is read from the CONCORDIA.APP layer: persona-masked SQL functions,
guarded semantic-view queries over the published metric grid, or governed APP procedures.
The app formats strings; it never computes a metric.
"""

from __future__ import annotations

import base64
import html
import json
import re
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Concordia", page_icon="◆", layout="wide", initial_sidebar_state="expanded")

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets" if (HERE / "assets").exists() else HERE.parent / "assets"
NAVY, BLUE, TEAL, SLATE, LINE, AMBER, RED = "#102A43", "#1746A2", "#0E9F9A", "#516D83", "#D4DEE8", "#B7791F", "#B42318"

METRICS = {
    "INBOUND_SUPPLIER_OTD": {
        "short": "Supplier on-time delivery", "team": "Procurement", "kind": "ratio", "code": "Inbound OTD",
        "question": "Did our suppliers deliver everything we ordered, by the date they promised?",
        "how": "Each purchase-order line counts once. It is on time only if the full accepted quantity arrived by the "
               "supplier's committed date. Parts that fail our quality check do not count as delivered.",
        "empty": "No supplier deliveries were due for this selection. Parts we build ourselves have no supplier orders.",
    },
    "OUTBOUND_CUSTOMER_OTD": {
        "short": "Customer on-time delivery", "team": "Logistics", "kind": "ratio", "code": "Outbound OTD",
        "question": "Did customers receive their whole order by the date we first promised?",
        "how": "Each customer order line counts once. It is on time only if everything arrived by the original promise date; "
               "moving the date later does not help. Arrived means the customer signed for it.",
        "empty": "No customer deliveries were due for this selection. Components are not sold to customers directly.",
    },
    "UNIT_FILL_RATE": {
        "short": "Fill rate", "team": "Logistics", "kind": "ratio", "code": "Unit fill rate",
        "question": "Of all the units customers ordered, how many did we ship?",
        "how": "Counts units, not orders, and ignores timing. Shipping more than was ordered does not count extra.",
        "empty": "No customer orders for this selection. Components are not sold to customers directly.",
    },
    "DAYS_INVENTORY": {
        "short": "Days of inventory", "team": "Planning", "kind": "days", "code": "Days of inventory",
        "question": "If production stopped today, how many days would our stock last?",
        "how": "Usable stock (on hand, minus units on quality hold or already promised to someone) compared with demand over "
               "the last 28 days. It is a snapshot on a date, not a monthly total.",
        "empty": "Days of inventory is published for finished motors at each site and across the network. Components are "
                 "used up in production, so they have no published stock cover. Choose a motor (MM-4xx).",
    },
    "LANDED_COST_PER_ACCEPTED_UNIT": {
        "short": "Landed cost per unit", "team": "Finance", "kind": "usd", "code": "Landed cost / unit",
        "question": "What did each accepted unit really cost us once it was here?",
        "how": "Supplier price plus freight, import duty, insurance and customs-broker fees, minus credits, per unit we accepted. "
               "If any bill is missing, no number is shown: a missing cost is never treated as zero.",
        "empty": "Nothing was bought from a supplier for this selection. Motors we build ourselves have no landed cost; "
                 "choose MM-440 or a purchased component.",
    },
}
STATUS_STYLE = {
    "COMPLETE": ("#E6F6F4", "#0B6E69"), "INCOMPLETE": ("#FDF3E1", "#8A5A12"), "ABSTAIN": ("#EEF1F5", "#44566C"),
    "ZERO_DENOMINATOR": ("#EEF1F5", "#44566C"), "ZERO_DEMAND": ("#EEF1F5", "#44566C"), "CLARIFY": ("#EAF0FD", "#1746A2"),
    "FORBIDDEN": ("#FDECEC", "#9B1C1C"), "REJECT": ("#FDECEC", "#9B1C1C"),
    "VERIFIED": ("#E6F6F4", "#0B6E69"), "DESCRIPTIVE": ("#EAF0FD", "#1746A2"), "UNVERIFIED": ("#FDECEC", "#9B1C1C"),
    "UNPINNED": ("#FDF3E1", "#8A5A12"), "REJECTED": ("#FDECEC", "#9B1C1C"),
    "WITHHELD": ("#FDF3E1", "#8A5A12"),
}
STATUS_LABEL = {
    "COMPLETE": "Complete", "INCOMPLETE": "Not final", "ABSTAIN": "Can't score", "ZERO_DENOMINATOR": "Nothing due",
    "ZERO_DEMAND": "No demand", "CLARIFY": "Which one?", "FORBIDDEN": "Hidden for your role", "REJECT": "Not a governed metric",
    "VERIFIED": "Matches this exact scope", "DESCRIPTIVE": "Facts, not a metric", "UNVERIFIED": "Did not match — not shown",
    "UNPINNED": "Scope not proven", "REJECTED": "Query refused", "WITHHELD": "Hidden for your role",
}
STATUS_PLAIN = {
    "COMPLETE": "All the information this number needs was available.",
    "INCOMPLETE": "Some information is still missing, so this is not final.",
    "ABSTAIN": "Key data is missing, so Concordia refuses to score this rather than guess.",
    "ZERO_DENOMINATOR": "Nothing was due in this period for this selection, so there is nothing to score. That is not the same as 0%.",
    "ZERO_DEMAND": "There was no recent demand, so days of cover is not meaningful.",
    "CLARIFY": "The question could mean more than one governed metric, so Concordia asks which one.",
    "FORBIDDEN": "Your role is not allowed to see this value.",
    "REJECT": "The term does not match any governed metric, so Concordia will not approximate it.",
    "VERIFIED": "Each number equals the governed answer published for that metric, month, known-as-of and scope. Nothing was recalculated.",
    "DESCRIPTIVE": "This answer counts or lists things in the ontology (parts, suppliers, sites). It is not one of the five governed metrics.",
    "UNVERIFIED": "The rows are not exactly the published answers for that scope, so the table is withheld.",
    "UNPINNED": "Metric, scope, known-as-of and month were not all fixed, so Concordia will not call this a match.",
    "REJECTED": "The request is unsupported or the generated query broke a governance rule, so no result is shown.",
    "WITHHELD": "This governed metric is hidden for the selected persona.",
}
REASON_PLAIN = {
    "BROKERAGE_AMOUNT_MISSING": "Customs-broker bill not in yet", "BUYER_CANCELLED": "We cancelled the order",
    "CALENDAR_MISSING": "Working-day calendar missing", "COUNTRY_MISSING": "Country of origin missing",
    "CREDIT_AMOUNT_MISSING": "Credit-note amount missing", "CUSTOMER_CANCELLED": "Customer cancelled",
    "CUSTOMER_HOLD": "Customer asked us to hold delivery", "DISPOSITION_MISSING": "Quality-check result missing",
    "DUTY_AMOUNT_MISSING": "Import-duty bill not in yet", "DUTY_FX_MISSING": "Exchange rate for duty missing",
    "FREIGHT_AMOUNT_MISSING": "Freight bill not in yet", "IDENTITY_UNRESOLVED": "Record could not be matched to a known part or company",
    "INCOTERM_MISSING": "Delivery terms missing", "INCOTERM_UNSUPPORTED": "Delivery terms not supported",
    "INSURANCE_AMOUNT_MISSING": "Insurance bill not in yet", "MERCHANDISE_AMOUNT_MISSING": "Supplier invoice not in yet",
    "MERCHANDISE_FX_MISSING": "Exchange rate for invoice missing", "TIMEZONE_MISSING": "Time zone missing",
    "UOM_UNRESOLVED": "Unknown unit of measure (for example kg vs pieces)", "ZERO_DEMAND": "No recent demand",
    "COST_NOT_ENTITLED": "Your role can't see cost", "SITE_NOT_ENTITLED": "Your role does not cover this site",
}
DRIVER_PLAIN = {
    "COMPANY_CANCELLED": "We cancelled the order", "FAILED_OR_MISDELIVERED": "Delivery failed or went to the wrong place",
    "LATE_DELIVERY": "Arrived late", "LATE_RECEIPT": "Supplier delivered late", "NOT_DELIVERED": "Not delivered yet",
    "NOT_SHIPPED": "Never shipped", "OPEN_PAST_DUE": "Still open and overdue", "PARTIAL_DELIVERY": "Only part of the order arrived",
    "PARTIAL_RECEIPT": "Supplier delivered only part", "PARTIAL_SHIPMENT": "Only part was shipped",
    "PROMISE_REVISED": "Promise date was moved; missed the original date", "SILENT_SUBSTITUTE": "A different part was shipped without approval",
    "SUPPLIER_CANCELLED": "Supplier cancelled", "SUPPLIER_REJECT": "Parts failed our quality check",
    "EXCLUDED": "Left out: data could not be trusted", "HIT": "On time and complete", "MISS": "Missed",
}
DIM_PLAIN = {"GEOGRAPHY": "Customer region", "FACILITY": "Site", "SUPPLIER": "Supplier", "CUSTOMER": "Customer", "ITEM": "Part"}
PAGES = {
    "Start here": "What Concordia is and how to read it",
    "Command center": "The five numbers, side by side",
    "Ask Concordia": "Ask a question in plain English",
    "Why it changed": "What went wrong this month vs last",
    "As-of replay": "How late paperwork changes an answer",
    "One graph": "How six systems' records join up",
    "Governance": "Definitions, access rules, audit trail",
}

st.markdown(
    f"""
<style>
  .stApp {{ background: radial-gradient(1200px 500px at 85% -10%, #E7EEF8 0%, #F5F7FA 55%) fixed; color: {NAVY}; }}
  .block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1440px; }}
  h1, h2, h3, h4 {{ color: {NAVY}; letter-spacing: -0.01em; }}
  section[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid {LINE}; }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label {{ border-radius: 10px; padding: 4px 8px; transition: background .12s; }}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{ background: #F1F5FA; }}
  .hero {{ background: linear-gradient(120deg, {NAVY} 0%, {BLUE} 62%, {TEAL} 100%); border-radius: 20px; padding: 26px 30px;
          color: #fff; margin-bottom: 16px; box-shadow: 0 12px 32px rgba(16,42,67,.18); }}
  .hero h1 {{ color: #fff; font-size: 2rem; margin: 0 0 6px 0; }}
  .hero p {{ color: #DCE8F5; margin: 0; font-size: 1.02rem; max-width: 900px; }}
  .hero .tag {{ display: inline-block; background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.28);
               border-radius: 999px; padding: 3px 12px; font-size: .78rem; margin-right: 6px; margin-top: 12px; color: #fff; }}
  .card {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 16px; padding: 16px 16px 12px 16px; height: 100%;
          min-height: 178px; box-shadow: 0 1px 2px rgba(16,42,67,.04); transition: box-shadow .15s, transform .15s, border-color .15s; }}
  .card:hover {{ box-shadow: 0 10px 26px rgba(16,42,67,.10); transform: translateY(-1px); border-color: #BFCFE0; }}
  .card.empty {{ background: repeating-linear-gradient(135deg, #FFFFFF 0 12px, #FAFBFD 12px 24px); border-style: dashed; }}
  .card .team {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; color: {SLATE}; font-weight: 700; }}
  .card .name {{ font-size: .98rem; font-weight: 650; color: {NAVY}; margin-top: 2px; }}
  .card .value {{ font-size: 2.1rem; font-weight: 750; color: {NAVY}; font-variant-numeric: tabular-nums; margin: 8px 0 4px 0; line-height: 1.1; }}
  .card .value.muted {{ color: #6B8199; font-size: 1.15rem; font-weight: 700; }}
  .card .why {{ font-size: .8rem; color: {SLATE}; line-height: 1.45; margin-top: 4px; }}
  .card .meta {{ font-size: .8rem; color: {SLATE}; margin-top: 6px; line-height: 1.45; }}
  .chip {{ display: inline-block; border-radius: 8px; padding: 2px 9px; font-size: .74rem; font-weight: 650; margin: 0 6px 6px 0;
          background: #EEF3FA; color: {BLUE}; border: 1px solid #D6E2F3; }}
  .chip.ok {{ background: #E6F6F4; color: #0B6E69; border-color: #C5EAE5; }}
  .chip.warn {{ background: #FDF3E1; color: #8A5A12; border-color: #F3DDB4; }}
  .explain {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 14px; padding: 14px 16px; font-size: .9rem; line-height: 1.55; }}
  .explain .k {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; color: {TEAL}; font-weight: 800; margin-bottom: 4px; }}
  .explain code {{ background: #F1F4F8; border-radius: 5px; padding: 0 5px; font-size: .82rem; }}
  .stButton > button {{ border-radius: 10px; border: 1px solid {LINE}; transition: all .12s; }}
  .stButton > button:hover {{ border-color: {BLUE}; color: {BLUE}; background: #F4F8FE; }}
  div[data-testid="stDataFrame"] {{ border: 1px solid {LINE}; border-radius: 12px; overflow: hidden; background: #FFFFFF; }}
  div[data-testid="stExpander"] details {{ border-radius: 12px; border-color: {LINE}; background: #FFFFFF; }}
  @media (max-width: 1100px) {{
    .card .value {{ font-size: 1.6rem; }}
    .card {{ min-height: 150px; padding: 12px; }}
    .hero h1 {{ font-size: 1.55rem; }}
  }}
  @media (max-width: 640px) {{
    .block-container {{ padding-left: .8rem; padding-right: .8rem; }}
    .hero {{ padding: 18px; border-radius: 14px; }}
    .tip .tt {{ width: 220px; }}
  }}
  .pill {{ display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: .72rem; font-weight: 700; letter-spacing: .02em; }}
  .reason {{ display: inline-block; background: #F1F4F8; color: #34495E; border-radius: 6px; padding: 1px 7px; font-size: .74rem;
            margin: 3px 4px 0 0; }}
  .section {{ font-size: 1.12rem; font-weight: 700; color: {NAVY}; margin: 18px 0 4px 0; }}
  .sub {{ color: {SLATE}; font-size: .9rem; margin-bottom: 10px; }}
  .intro {{ background: #FFFFFF; border: 1px solid {LINE}; border-left: 5px solid {BLUE}; border-radius: 12px; padding: 12px 16px; margin-bottom: 12px; }}
  .intro .t {{ font-size: 1.35rem; font-weight: 750; color: {NAVY}; }}
  .intro .a {{ color: {NAVY}; font-size: .95rem; margin-top: 2px; }}
  .intro .h {{ color: {SLATE}; font-size: .85rem; margin-top: 4px; }}
  .answer {{ background: #FFFFFF; border: 1px solid {LINE}; border-left: 5px solid {TEAL}; border-radius: 14px; padding: 18px 20px; }}
  .answer .q {{ color: {SLATE}; font-size: .85rem; margin-bottom: 6px; }}
  .answer .n {{ font-size: 1.05rem; line-height: 1.55; color: {NAVY}; }}
  .kv {{ font-size: .8rem; color: {SLATE}; }}
  .kv b {{ color: {NAVY}; font-weight: 650; }}
  .disclosure {{ background: #FFF8EB; border: 1px solid #F3D9A4; color: #6B4A0E; border-radius: 10px; padding: 8px 12px; font-size: .82rem; }}
  .persona {{ background: #F5F7FA; border: 1px solid {LINE}; border-radius: 12px; padding: 10px 12px; font-size: .84rem; }}
  .story {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 14px; padding: 14px 16px; height: 100%; }}
  .story b {{ color: {NAVY}; }}
  .story .k {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; color: {SLATE}; font-weight: 700; }}
  .tip {{ position: relative; display: inline-block; cursor: help; color: {SLATE}; font-size: .72rem; font-weight: 700; font-style: normal;
         margin-left: 6px; border: 1px solid #B8C7D6; border-radius: 50%; width: 17px; height: 17px; line-height: 15px; text-align: center;
         background: #FFFFFF; vertical-align: middle; letter-spacing: 0; text-transform: none; }}
  .tip .tt {{ visibility: hidden; opacity: 0; position: absolute; z-index: 10000; top: 22px; left: 50%; transform: translateX(-50%);
             width: 300px; background: {NAVY}; color: #F5F7FA; text-align: left; font-weight: 400; font-size: .8rem; line-height: 1.5;
             border-radius: 10px; padding: 10px 12px; box-shadow: 0 8px 24px rgba(16,42,67,.28); transition: opacity .12s; }}
  .tip .tt b {{ color: #FFFFFF; }}
  .tip:hover .tt {{ visibility: visible; opacity: 1; }}
  div[data-testid="stMarkdownContainer"], div[data-testid="stColumn"], div[data-testid="column"] {{ overflow: visible !important; }}
  div[data-testid="stMetricValue"] {{ color: {NAVY}; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 6px; }}
  .stTabs [data-baseweb="tab"] {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 10px 10px 0 0; padding: 6px 14px; }}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- Snowflake session and reads
@st.cache_resource
def session():
    try:
        from snowflake.snowpark.context import get_active_session

        # Streamlit in Snowflake runs with owner's rights: USE statements are rejected and secondary roles do not apply.
        return get_active_session()
    except Exception:  # noqa: BLE001 - local run against the same account
        import sys

        import snowflake.connector
        from snowflake.snowpark import Session

        snowflake.connector.paramstyle = "qmark"

        sys.path.insert(0, str(HERE.parent / "scripts"))
        from sf import connect

        active = Session.builder.configs({"connection": connect()}).create()
        active.sql("USE ROLE CONCORDIA_APP_OWNER").collect()
        active.sql("USE SECONDARY ROLES NONE").collect()
        active.sql("USE WAREHOUSE CONCORDIA_APP_WH").collect()
        return active


DATE_COLUMNS = ("PERIOD_START", "PERIOD_END", "PERIOD_DATE", "COMMITMENT_ON", "COMPLETED_ON")


def iso_day(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)[:10]


def inline_nulls(sql: str, params: list) -> tuple[str, list]:
    # Streamlit in Snowflake does not bind Python None as SQL NULL, so absent filters are written as NULL literals.
    pieces = sql.split("?")
    if len(pieces) - 1 != len(params):
        raise ValueError("placeholder count does not match parameters")
    text, bound = pieces[0], []
    for value, piece in zip(params, pieces[1:]):
        if value is None:
            text += "NULL" + piece
        else:
            text += "?" + piece
            bound.append(value)
    return text, bound


def q(sql: str, params: list | None = None) -> pd.DataFrame:
    sql, bound = inline_nulls(sql, params or [])
    # Date dtypes differ between Streamlit in Snowflake and a local run, so calendar dates are held as YYYY-MM-DD text.
    frame = session().sql(sql, params=bound).to_pandas()
    for column in DATE_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].map(iso_day).astype(object)
    return frame


@st.cache_data(ttl=120, show_spinner=False)
def personas() -> pd.DataFrame:
    return q("SELECT PERSONA, DISPLAY_NAME, TITLE, COST_VISIBLE, AUDIT_VISIBLE, ALLOWED_FACILITIES FROM CONCORDIA.APP.V_ENTITLEMENT "
             "ORDER BY PERSONA")


@st.cache_data(ttl=120, show_spinner=False)
def results(persona: str, item=None, facility=None, geo=None, supplier=None, customer=None) -> pd.DataFrame:
    return q("SELECT * FROM TABLE(CONCORDIA.APP.RESULTS_FOR(?, ?::VARCHAR, ?::VARCHAR, ?::VARCHAR, ?::VARCHAR, ?::VARCHAR))",
             [persona, item, facility, geo, supplier, customer])


@st.cache_data(ttl=120, show_spinner=False)
def breakdown(persona: str, metric: str, period: str, kind: str, dim: str, item=None) -> pd.DataFrame:
    return q("SELECT * FROM TABLE(CONCORDIA.APP.BREAKDOWN_FOR(?, ?, ?::DATE, ?, ?, ?::VARCHAR)) ORDER BY DIM_VALUE",
             [persona, metric, period, kind, dim, item])


@st.cache_data(ttl=120, show_spinner=False)
def receipts(persona: str, period: str, kind: str, item=None, facility=None) -> pd.DataFrame:
    return q("SELECT * FROM TABLE(CONCORDIA.APP.RECEIPTS_FOR(?, ?::DATE, ?, ?::VARCHAR, ?::VARCHAR)) ORDER BY RECEIPT_ID",
             [persona, period, kind, item, facility])


@st.cache_data(ttl=120, show_spinner=False)
def table(name: str, where: str = "", params: tuple = (), limit: int = 2000) -> pd.DataFrame:
    return q(f"SELECT * FROM CONCORDIA.APP.{name} {where} LIMIT {int(limit)}", list(params))


@st.cache_data(ttl=60, show_spinner=False)
def publish_runs() -> pd.DataFrame:
    return q("SELECT RUN_ID, STARTED_AT, FINISHED_AT, RAW_RECORDS, RESULT_ROWS, RECENCY FROM CONCORDIA.APP.V_PUBLISH_RUN ORDER BY RECENCY")


@st.cache_data(ttl=300, show_spinner=False)
def dims() -> dict:
    items = q("SELECT ITEM_ID, NAME, ITEM_TYPE, FAMILY FROM CONCORDIA.APP.V_ITEM ORDER BY IFF(ITEM_TYPE = 'FINISHED', 0, 1), ITEM_ID")
    facilities = q("SELECT FACILITY_ID, NAME, KIND FROM CONCORDIA.APP.V_FACILITY ORDER BY KIND DESC, FACILITY_ID")
    geos = q("SELECT GEOGRAPHY_ID, NAME FROM CONCORDIA.APP.V_GEOGRAPHY ORDER BY GEOGRAPHY_ID")
    parties = q("SELECT PARTY_ID, NAME, PARTY_TYPE FROM CONCORDIA.APP.V_PARTY")
    questions = q("SELECT QUESTION_ID, METRIC_ID, SCOPE, PERIOD_START, AS_OF_KIND, COMPARE_TO, QUESTION "
                  "FROM CONCORDIA.APP.V_VERIFIED_QUESTION ORDER BY QUESTION_ID")
    return {"items": items, "facilities": facilities, "geos": geos, "parties": parties, "questions": questions}


def svg(name: str) -> str:
    path = ASSETS / name
    if not path.exists():
        return ""
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()


# ---------------------------------------------------------------- formatting (strings only)
def esc(text) -> str:
    # Streamlit markdown reads paired dollar signs as maths, so they are written as entities.
    return html.escape(str(text), quote=True).replace("$", "&#36;")


def tip(body: str) -> str:
    return f'<span class="tip">i<span class="tt">{body}</span></span>'


def trim(number) -> str:
    text = str(number)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def plain_reason(code: str) -> str:
    return REASON_PLAIN.get(code, code.replace("_", " ").capitalize())


def plain_driver(code) -> str:
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return "—"
    return DRIVER_PLAIN.get(code, str(code).replace("_", " ").capitalize())


def as_list(value) -> list:
    if isinstance(value, str):
        return json.loads(value or "[]")
    return list(value or [])


def pill(status: str | None) -> str:
    bg, fg = STATUS_STYLE.get(status or "", ("#EEF1F5", "#44566C"))
    label = STATUS_LABEL.get(status or "", status or "—")
    return (f'<span class="pill" style="background:{bg};color:{fg}" title="{esc(status or "")}">{esc(label)}</span>'
            f'{tip(esc(STATUS_PLAIN.get(status or "", "No published value.")) + "<br><br>Code: <b>" + esc(status or "none") + "</b>")}')


def reasons_html(reasons) -> str:
    return "".join(f'<span class="reason" title="{esc(r)}">{esc(plain_reason(r))}</span>' for r in as_list(reasons))


def present(value) -> bool:
    return isinstance(value, str) and value != ""


MISSING = "—"


def blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in ("", "none", "nan", "nat", "null")
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def tidy(frame: pd.DataFrame) -> pd.DataFrame:
    """Display copy only: absent values read as a dash, never as None, nan or NaT."""
    out = frame.copy()
    for column in out.columns:
        if out[column].map(blank).any():
            # A column mixing numbers and dashes is held as text so Arrow serialisation never fails.
            out[column] = out[column].astype(object).map(lambda v: MISSING if blank(v) else (v if isinstance(v, str) else trim(v)))
    return out


def show(where, frame: pd.DataFrame, **kwargs):
    kwargs.setdefault("hide_index", True)
    kwargs.setdefault("use_container_width", True)
    where.dataframe(tidy(frame), **kwargs)


EMPTY_HEAD = {
    "INBOUND_SUPPLIER_OTD": "No supplier deliveries due",
    "OUTBOUND_CUSTOMER_OTD": "No customer deliveries due",
    "UNIT_FILL_RATE": "No customer orders",
    "DAYS_INVENTORY": "No stock snapshot",
    "LANDED_COST_PER_ACCEPTED_UNIT": "No goods received",
}
EMPTY_NOUN = {
    "INBOUND_SUPPLIER_OTD": "supplier order lines were due",
    "OUTBOUND_CUSTOMER_OTD": "customer order lines were due",
    "UNIT_FILL_RATE": "customer orders were placed",
    "DAYS_INVENTORY": "stock snapshot was published",
    "LANDED_COST_PER_ACCEPTED_UNIT": "goods were received from a supplier",
}


def gap(metric: str, data: pd.DataFrame, kind: str, month) -> dict:
    """Why a card has no published row: the measure never applies here, or nothing happened in this month."""
    history = data[(data.RECENCY == 1) & (data.METRIC_ID == metric) & (data.AS_OF_KIND == kind)]
    months = sorted({m for m in history.PERIOD_START.map(iso_day) if m})
    if not months:
        return {"headline": "Does not apply here", "why": METRICS[metric]["empty"], "near": [], "applies": False}
    target = iso_day(month) or ""
    earlier = [m for m in months if m < target][-1:]
    later = [m for m in months if m > target][:1]
    near = earlier + later
    hint = " Closest months with data: " + " and ".join(month_label(m) for m in near) + "." if near else ""
    return {"headline": EMPTY_HEAD[metric],
            "why": f"No {EMPTY_NOUN[metric]} in {month_label(month)} for this selection, so there is nothing to score. "
                   f"That is not 0%.{hint}",
            "near": near, "applies": True}


PICKER_KEYS = ("cc_month", "bridge_month", "asof_month")


def jump(month: str):
    # Pickers re-read focus_month when their own state is cleared; a month outside a picker's options is never forced on it.
    st.session_state.focus_month = month
    for key in PICKER_KEYS:
        st.session_state.pop(key, None)


def jump_buttons(where, info: dict | None, key: str):
    if not info or not info.get("near"):
        return
    for m in info["near"]:
        where.button(f"Go to {month_label(m)} →", key=f"{key}_{m}", on_click=jump, args=(m,), use_container_width=True)


def plain_sentence(metric: str, row, info: dict | None = None) -> str:
    """One plain-English line built only from strings the governed SQL already returned."""
    m = METRICS[metric]
    if row is None:
        return (info or {}).get("why") or m["empty"]
    status = row.get("STATUS")
    n, d, shown = row.get("NUMERATOR"), row.get("DENOMINATOR"), row.get("DISPLAY")
    if status == "FORBIDDEN":
        return "Your role is not allowed to see cost, so this value is hidden by the database, not by the app."
    if status in ("ZERO_DENOMINATOR", "ZERO_DEMAND", "ABSTAIN", "CLARIFY"):
        reasons = ", ".join(plain_reason(r) for r in as_list(row.get("REASONS")))
        return STATUS_PLAIN[status] + (f" Reason: {reasons}." if reasons else "")
    text = ""
    if metric == "INBOUND_SUPPLIER_OTD" and present(n) and present(d):
        text = f"{trim(n)} of {trim(d)} supplier order lines arrived complete and on time."
    elif metric == "OUTBOUND_CUSTOMER_OTD" and present(n) and present(d):
        text = f"{trim(n)} of {trim(d)} customer order lines arrived complete by the date we first promised."
    elif metric == "UNIT_FILL_RATE" and present(n) and present(d):
        text = f"{trim(n)} of {trim(d)} ordered units were shipped."
    elif metric == "DAYS_INVENTORY" and present(shown):
        text = f"Usable stock would cover about {trim(shown)} days of demand."
    elif metric == "LANDED_COST_PER_ACCEPTED_UNIT" and present(shown):
        text = f"Each accepted unit cost ${shown} once freight, duty, insurance and broker fees are added."
    if status == "INCOMPLETE":
        reasons = ", ".join(plain_reason(r) for r in as_list(row.get("REASONS")))
        if metric == "LANDED_COST_PER_ACCEPTED_UNIT":
            text = "No true cost yet, and Concordia will not guess."
        text += f" Not final: {reasons or 'some inputs are missing'}."
    return text.strip() or STATUS_PLAIN.get(status or "", "No published value.")


def headline(metric: str, row, info: dict | None = None) -> str:
    kind = METRICS[metric]["kind"]
    if row is None:
        return f'<div class="value muted">{esc((info or {}).get("headline") or EMPTY_HEAD[metric])}</div>'
    if not present(row.get("DISPLAY")):
        if row.get("STATUS") == "INCOMPLETE" and present(row.get("DIAGNOSTIC_DISPLAY")):
            return f'<div class="value muted">Not final <span style="font-size:.85rem">(partial ${esc(row["DIAGNOSTIC_DISPLAY"])})</span></div>'
        if row.get("STATUS") == "FORBIDDEN":
            return '<div class="value muted">Hidden for your role</div>'
        return f'<div class="value muted">{esc(STATUS_LABEL.get(row.get("STATUS") or "", "Not published"))}</div>'
    if kind == "ratio" and present(row.get("PERCENT_DISPLAY")):
        return f'<div class="value">{esc(row["PERCENT_DISPLAY"])}<span style="font-size:1.1rem">%</span></div>'
    if kind == "usd":
        return f'<div class="value">&#36;{esc(row["DISPLAY"])}</div>'
    if kind == "days":
        return f'<div class="value">{esc(trim(row["DISPLAY"]))}<span style="font-size:1rem"> days</span></div>'
    return f'<div class="value">{esc(row["DISPLAY"])}</div>'


def card(metric: str, row, note: str = "", title: str | None = None, info: dict | None = None) -> str:
    m = METRICS[metric]
    if row is None:
        body = (f"<b>{esc(m['question'])}</b><br><br>{esc(m['how'])}<br><br>Owner: {esc(m['team'])} · governed name: {esc(m['code'])}")
        why = (info or {}).get("why") or m["empty"]
        return (f'<div class="card empty"><div class="team">{esc(m["team"])}</div>'
                f'<div class="name">{esc(title or m["short"])}{tip(body)}</div>'
                f'{headline(metric, None, info)}<div class="why">{esc(why)}</div></div>')
    meta = []
    if row is not None:
        if present(row.get("NUMERATOR")) and present(row.get("DENOMINATOR")) and m["kind"] == "ratio":
            meta.append(f"{trim(row['NUMERATOR'])} of {trim(row['DENOMINATOR'])}")
        if present(row.get("COVERAGE")):
            coverage = trim(row["COVERAGE"])
            meta.append({"1": "all data present", "0": "no supporting data yet"}.get(coverage, f"data coverage {coverage} of 1"))
        if row.get("AFFECTED_COMMITMENTS") and int(row["AFFECTED_COMMITMENTS"]) > 0:
            meta.append(f"{int(row['AFFECTED_COMMITMENTS'])} missed or left out")
    if note:
        meta.append(note)
    body = (f"<b>{esc(m['question'])}</b><br><br>{esc(m['how'])}<br><br><b>Right now:</b> {esc(plain_sentence(metric, row))}"
            f"<br><br>Owner: {esc(m['team'])} · governed name: {esc(m['code'])}")
    status = row.get("STATUS") if row is not None else None
    return (f'<div class="card"><div class="team">{esc(m["team"])}</div>'
            f'<div class="name">{esc(title or m["short"])}{tip(body)}</div>'
            f'{headline(metric, row)}<div>{pill(status) if status else ""}</div>'
            f'<div class="meta">{esc(" · ".join(meta))}</div>'
            f'<div>{reasons_html(row.get("REASONS")) if row is not None else ""}</div></div>')


def intro(title: str, answers: str, how: str):
    st.markdown(f'<div class="intro"><div class="t">{esc(title)}</div><div class="a">{esc(answers)}</div>'
                f'<div class="h">{esc(how)}</div></div>', unsafe_allow_html=True)


def section(title: str, explain: str, sub: str = ""):
    st.markdown(f'<div class="section">{esc(title)}{tip(esc(explain))}</div>' + (f'<div class="sub">{esc(sub)}</div>' if sub else ""),
                unsafe_allow_html=True)


def month_options(series: pd.Series) -> list[str]:
    return sorted({v for v in series.map(iso_day) if v})


def month_label(value) -> str:
    day = iso_day(value)
    if not day:
        return "—"
    try:
        return datetime.strptime(day, "%Y-%m-%d").strftime("%b %Y")
    except ValueError:
        return day


def day_label(value) -> str:
    try:
        return pd.Timestamp(value).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return "—"


def in_month(series: pd.Series, month) -> pd.Series:
    return series.map(iso_day) == iso_day(month)


def pick(frame: pd.DataFrame, **match):
    sub = frame
    for key, value in match.items():
        sub = sub[sub[key] == value]
    return None if sub.empty else sub.iloc[0].to_dict()


def scope_of(question_row) -> dict:
    raw = question_row.get("SCOPE") if question_row is not None else None
    return json.loads(raw) if isinstance(raw, str) and raw else (raw or {})


# ---------------------------------------------------------------- shared context
roster = personas()
D = dims()
ITEM_NAMES = dict(zip(D["items"].ITEM_ID, D["items"].NAME))
ITEM_TYPES = dict(zip(D["items"].ITEM_ID, D["items"].ITEM_TYPE))
FAC_NAMES = dict(zip(D["facilities"].FACILITY_ID, D["facilities"].NAME))
GEO_NAMES = dict(zip(D["geos"].GEOGRAPHY_ID, D["geos"].NAME))
PARTY_NAMES = dict(zip(D["parties"].PARTY_ID, D["parties"].NAME))
LEAD = D["questions"].iloc[0].to_dict() if not D["questions"].empty else None
LEAD_SCOPE = scope_of(LEAD)


def question_scope(metric: str, compare: str | None = None) -> dict:
    for row in D["questions"].to_dict("records"):
        if row["METRIC_ID"] == metric and (compare is None or row.get("COMPARE_TO") == compare):
            return scope_of(row)
    return {}


def item_label(i) -> str:
    if i is None:
        return "All parts"
    kind = "motor" if ITEM_TYPES.get(i) == "FINISHED" else "component"
    return f"{i} · {ITEM_NAMES.get(i, '')} ({kind})"


def nice(dim: str, value: str) -> str:
    names = {"FACILITY": FAC_NAMES, "GEOGRAPHY": GEO_NAMES, "SUPPLIER": PARTY_NAMES, "CUSTOMER": PARTY_NAMES, "ITEM": ITEM_NAMES}[dim]
    return f"{names.get(value, value)}"


def go(target: str):
    st.session_state.nav = target


def site_list(allowed) -> str:
    sites = as_list(allowed)
    return "all" if "*" in sites else ", ".join(FAC_NAMES.get(s, s) for s in sites)


# ---------------------------------------------------------------- sidebar
logo = svg("concordia-logo.svg")
with st.sidebar:
    if logo:
        st.markdown(f'<img src="{logo}" style="width:100%;margin:4px 0 10px 0">', unsafe_allow_html=True)
    labels = {r.PERSONA: f"{r.DISPLAY_NAME} — {r.TITLE}" for r in roster.itertuples()}
    persona = st.selectbox("Viewing as", list(labels), index=list(labels).index("EXECUTIVE") if "EXECUTIVE" in labels else 0,
                           format_func=lambda p: labels[p], key="persona",
                           help="Pick whose eyes you are looking through. The database decides what each role may see: "
                                "planners and logistics cannot see cost, and logistics sees only Americas sites. Where two roles "
                                "can both see a number, it is the same number.")
    me = roster[roster.PERSONA == persona].iloc[0]
    st.markdown(
        f'<div class="persona"><b>{esc(me.DISPLAY_NAME)}</b><br>{esc(me.TITLE)}<br>'
        f'Cost {"visible" if me.COST_VISIBLE else "hidden"} · Audit trail {"everyone" if me.AUDIT_VISIBLE else "own questions"}<br>'
        f'Sites {esc(site_list(me.ALLOWED_FACILITIES))}</div>',
        unsafe_allow_html=True)
    st.write("")
    page = st.radio("Go to", list(PAGES), captions=list(PAGES.values()), key="nav")
    st.markdown("**Focus**", help="These two choices follow you across pages, so every page talks about the same part and month.")
    item_ids = list(D["items"].ITEM_ID)
    lead_item = LEAD_SCOPE.get("item_id")
    focus_item = st.selectbox("Part", [None] + item_ids,
                              index=([None] + item_ids).index(lead_item) if lead_item in item_ids else 0, format_func=item_label,
                              key="focus_item", help="Motors are what we sell. Components are what we buy to build them. "
                                                     "Type to search.")
    runs = publish_runs()
    if not runs.empty:
        latest = runs.iloc[0]
        st.markdown(
            f'<div class="kv" style="margin-top:14px">Last refreshed <b>{pd.Timestamp(latest.FINISHED_AT).strftime("%d %b %Y %H:%M UTC")}</b><br>'
            f'<b>{int(latest.RAW_RECORDS):,}</b> source records · <b>{int(latest.RESULT_ROWS):,}</b> governed answers</div>',
            unsafe_allow_html=True)
    st.markdown('<div class="disclosure" style="margin-top:12px">Synthetic world CONCORDIA_SIM_V1. No customer, partner or '
                'industry data. Personas are demo identities on one Snowflake role.</div>', unsafe_allow_html=True)

BASE = results(persona)
MONTHS = month_options(BASE.PERIOD_START)
FLOW_MONTHS = month_options(BASE[BASE.METRIC_ID != "DAYS_INVENTORY"].PERIOD_START)
FINAL_ROWS = BASE[BASE.AS_OF_KIND == "final"]
FINAL_AS_OF = day_label(FINAL_ROWS.AS_OF.max()) if not FINAL_ROWS.empty else "latest load"


def early_as_of(frame: pd.DataFrame, month) -> str:
    rows = frame[(frame.AS_OF_KIND == "early") & in_month(frame.PERIOD_START, month)]
    return day_label(rows.AS_OF.iloc[0]) if not rows.empty else "5th of the next month"


def default_metric(frame: pd.DataFrame, options: list[str]) -> str:
    """The lead verified question's measure when this scope has values for it, otherwise the first measure that does."""
    with_values = set(frame[frame.VALUE_NUM.notna()].METRIC_ID)
    preferred = [LEAD["METRIC_ID"]] if LEAD else []
    for metric in preferred + options:
        if metric in options and metric in with_values:
            return metric
    return options[0]


def month_picker(where, key: str, choices: list[str] | None = None):
    choices = choices or MONTHS
    lead_month = iso_day(LEAD.get("PERIOD_START")) if LEAD else None
    current = st.session_state.get("focus_month", lead_month)
    index = choices.index(current) if current in choices else len(choices) - 1
    picked = where.selectbox("Month", choices, index=index, format_func=month_label, key=key,
                             help="The calendar month being measured. Shared across pages.")
    st.session_state.focus_month = picked
    return picked


# ---------------------------------------------------------------- pages
def page_start():
    st.markdown(
        '<div class="hero"><h1>Different teams. Same truth.</h1>'
        '<p>Five teams look at the same business through five different systems and get five different answers. '
        'Concordia gives every team one answer, with its definition, its evidence and what is still missing.</p>'
        '<span class="tag">ERP · MES · WMS · TMS · CRM</span><span class="tag">5 governed metrics</span>'
        '<span class="tag">Runs inside Snowflake</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section">The pretend company</div>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.markdown('<div class="story"><div class="k">Who</div><b>Meridian Motion</b> builds electric motors in three factories '
               '(Dayton, Reno, Stuttgart), stores them in three warehouses (Newark, Oakland, Hamburg) and delivers to 24 customers '
               'in six regions. It buys parts from 40 suppliers.</div>', unsafe_allow_html=True)
    b.markdown('<div class="story"><div class="k">What goes wrong</div>Customers get only part of an order. Deliveries to one '
               'region run late. A promise date gets quietly moved. A batch of supplier parts fails inspection. The freight bill '
               'arrives weeks later. Each system uses its own codes and units.</div>', unsafe_allow_html=True)
    c.markdown('<div class="story"><div class="k">What Concordia does</div>Writes each measure down once, calculates it once inside '
               'Snowflake, refuses to guess when data is missing, remembers what was known on each date, and shows the evidence '
               'behind every number.</div>', unsafe_allow_html=True)
    motors = int((D["items"].ITEM_TYPE == "FINISHED").sum())
    components = int(len(D["items"]) - motors)
    span = f"{month_label(FLOW_MONTHS[0])} to {month_label(FLOW_MONTHS[-1])}" if FLOW_MONTHS else "no months yet"
    st.markdown(
        f'<div class="explain" style="margin-top:12px"><div class="k">How much data is here</div>'
        f'<b>{len(FLOW_MONTHS)} months</b> ({esc(span)}) · <b>{motors}</b> motors · <b>{components}</b> components. Every part, '
        f'site, region, supplier and customer is published for every month it had activity, not only the demo story '
        f'(MM-440 in May 2026). Small selections are thin, though: one motor in one customer region often has only '
        f'1 to 5 order lines in a month, and some months have none. Those show as <b>No customer deliveries due</b>, which is '
        f'not 0%. Pick All parts or a whole part for steadier numbers.</div>', unsafe_allow_html=True)
    st.markdown('<div class="section">The five numbers, in plain words</div>', unsafe_allow_html=True)
    cols = st.columns(5)
    for col, (metric, m) in zip(cols, METRICS.items()):
        col.markdown(f'<div class="story"><div class="k">{esc(m["team"])}</div><b>{esc(m["short"])}</b><br>{esc(m["question"])}</div>',
                     unsafe_allow_html=True)
    st.markdown('<div class="section">Where to go</div>', unsafe_allow_html=True)
    grid = st.columns(3)
    for i, (name, caption) in enumerate(list(PAGES.items())[1:]):
        with grid[i % 3]:
            st.button(f"{name}: {caption}", key=f"go{i}", on_click=go, args=(name,), use_container_width=True)
    st.markdown('<div class="section">How to read a card</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Hover over any <span class="tip" style="margin-left:0">i<span class="tt">Like this. Every card, '
                'label and chart has one.</span></span> icon for a plain-English explanation. A grey label such as '
                '<span class="reason">Freight bill not in yet</span> says why a number is not final. <b>Final</b> means what we know '
                'today; <b>Early</b> means what we knew on the 5th of the following month.</div>', unsafe_allow_html=True)


def card_row(data: pd.DataFrame, metric: str, kind: str, month):
    if metric == "DAYS_INVENTORY":
        m4 = data[(data.RECENCY == 1) & (data.METRIC_ID == metric) & (data.AS_OF_KIND == kind)]
        return pick(m4[in_month(m4.PERIOD_START, month)]) if kind == "early" else pick(m4)
    current = data[(data.RECENCY == 1) & (data.AS_OF_KIND == kind) & in_month(data.PERIOD_START, month)]
    return pick(current, METRIC_ID=metric)


def value_text(metric: str, row, info: dict | None = None) -> str:
    if row is None:
        return (info or {}).get("headline") or EMPTY_HEAD[metric]
    if row.get("STATUS") == "FORBIDDEN":
        return "Hidden for this role"
    if not present(row.get("DISPLAY")):
        return STATUS_LABEL.get(row.get("STATUS"), "Not published")
    kind = METRICS[metric]["kind"]
    if kind == "ratio" and present(row.get("PERCENT_DISPLAY")):
        return f'{row["PERCENT_DISPLAY"]}% ({trim(row["NUMERATOR"])} of {trim(row["DENOMINATOR"])})'
    if kind == "usd":
        return f'${row["DISPLAY"]}'
    if kind == "days":
        return f'{trim(row["DISPLAY"])} days'
    return str(row["DISPLAY"])


COVERAGE_STATE = {"COMPLETE": "Complete", "INCOMPLETE": "Not final", "ABSTAIN": "Can't score", "ZERO_DENOMINATOR": "Nothing due",
                  "ZERO_DEMAND": "Nothing due", "FORBIDDEN": "Hidden for your role"}
COVERAGE_COLORS = {"Complete": TEAL, "Not final": "#E3A33B", "Can't score": "#8CA0B3", "Nothing due": "#C9D5E2",
                   "Hidden for your role": "#E7A1A1", "No activity": "#EEF2F6"}


def coverage_map(data: pd.DataFrame, kind: str, month):
    section("Where this selection has data",
            "Each square is one measure in one month for the part and scope chosen above. Grey means nothing happened that month "
            "(no orders due, no goods received), which is different from a score of zero. Hover a square for the governed value.",
            "Pick a coloured month in the Month box to see its cards.")
    metrics = [m for m in METRICS if m != "DAYS_INVENTORY"]
    rows = data[(data.RECENCY == 1) & (data.AS_OF_KIND == kind) & data.METRIC_ID.isin(metrics)]
    lookup = {(r["METRIC_ID"], iso_day(r["PERIOD_START"])): r for r in rows.to_dict("records")}
    selected = iso_day(month)
    cells = []
    for metric in metrics:
        for m in FLOW_MONTHS:
            r = lookup.get((metric, m))
            if r is None:
                state, shown, counted, out_of = "No activity", "Nothing happened this month", MISSING, MISSING
            else:
                state = COVERAGE_STATE.get(r["STATUS"], STATUS_LABEL.get(r["STATUS"], "Not published"))
                shown = r["DISPLAY"] if present(r.get("DISPLAY")) else state
                counted = trim(r["NUMERATOR"]) if present(r.get("NUMERATOR")) else MISSING
                out_of = trim(r["DENOMINATOR"]) if present(r.get("DENOMINATOR")) else MISSING
            cells.append({"Measure": METRICS[metric]["short"], "Month": month_label(m), "Order": m, "State": state,
                          "Governed value": shown, "Counted": counted, "Out of": out_of, "Selected": m == selected})
    frame = pd.DataFrame(cells)
    if frame.empty:
        return
    order = [METRICS[m]["short"] for m in metrics]
    x = alt.X("Month:N", sort=alt.EncodingSortField(field="Order", order="ascending"), title=None, axis=alt.Axis(labelAngle=-40))
    y = alt.Y("Measure:N", sort=order, title=None, axis=alt.Axis(labelLimit=240))
    tiles = (alt.Chart(frame).mark_rect(cornerRadius=4, stroke="#FFFFFF", strokeWidth=2)
             .encode(x=x, y=y,
                     color=alt.Color("State:N", scale=alt.Scale(domain=list(COVERAGE_COLORS), range=list(COVERAGE_COLORS.values())),
                                     legend=alt.Legend(orient="top", title=None)),
                     tooltip=["Measure", "Month", "State", "Governed value", "Counted", "Out of"]))
    marker = (alt.Chart(frame[frame.Selected]).mark_rect(filled=False, stroke=NAVY, strokeWidth=2.5, cornerRadius=4)
              .encode(x=x, y=y))
    st.altair_chart((tiles + marker).properties(height=200), use_container_width=True)
    active = frame[frame.State != "No activity"]
    if active.empty:
        st.caption("Nothing was recorded for this selection in any month. Try All parts, another part, or a wider scope.")
    else:
        st.caption(f"{active.Order.nunique()} of {len(FLOW_MONTHS)} months have at least one published answer for this selection.")


def page_command_center():
    intro("Command center", "How did this part do this month, through each team's eyes?",
          "Five cards, one per team. Hover the i on a card for what it measures and what this value means.")
    if not MONTHS:
        st.info("No published periods yet.")
        return
    c1, c2, c3 = st.columns([1.1, 1.3, 1.6])
    month = month_picker(c1, "cc_month")
    item = focus_item
    kind = c2.selectbox("Known as of", ["final", "early"],
                        format_func=lambda k: f"Final (what we know on {FINAL_AS_OF})" if k == "final"
                        else f"Early (what we knew on {early_as_of(BASE, month)})",
                        help="Late paperwork can change an answer. Early shows the answer as it looked shortly after the month ended.")
    lens = c3.selectbox("Narrow to", ["Everywhere", "One site", "One customer region"],
                        help="Optional. A site is a factory or warehouse; a region is where the customer is.")
    facility = geo = None
    if lens == "One site":
        facility = c3.selectbox("Site", list(D["facilities"].FACILITY_ID), format_func=lambda f: FAC_NAMES.get(f, f))
    elif lens == "One customer region":
        geo = c3.selectbox("Region", list(D["geos"].GEOGRAPHY_ID), format_func=lambda g: GEO_NAMES.get(g, g))
    data = results(persona, item, facility, geo)
    current = data[(data.RECENCY == 1) & (data.AS_OF_KIND == kind) & in_month(data.PERIOD_START, month)]
    st.markdown(f'<div class="section">{esc(month_label(month))} · {esc(item_label(item))}'
                f'{" · " + esc(FAC_NAMES.get(facility, "")) if facility else ""}{" · " + esc(GEO_NAMES.get(geo, "")) if geo else ""}</div>',
                unsafe_allow_html=True)
    if persona == "LOGISTICS" and facility is None:
        scope_word = "region" if geo else "enterprise"
        st.info(f"Shared {scope_word} aggregate: site-detail entitlement does not redefine this number. "
                "It may include contributions from sites whose detail rows Logistics cannot inspect.")
    cols = st.columns(5)
    for col, metric in zip(cols, METRICS):
        row = card_row(data, metric, kind, month)
        info = gap(metric, data, kind, month) if row is None else None
        note = f"stock snapshot on {day_label(row['AS_OF'])}" if metric == "DAYS_INVENTORY" and row is not None else ""
        col.markdown(card(metric, row, note, info=info), unsafe_allow_html=True)
        jump_buttons(col, info, f"cc_{metric}")

    coverage_map(data, kind, month)

    section("Same question, three teams",
            "Planning, procurement and logistics each ask for this selection. The database answers each one separately with its own "
            "access rules. Shared measures must match exactly; cost is hidden from roles that may not see it.",
            "Live check: three separate database reads, compared as text.")
    teams = [p for p in ("PLANNER", "PROCUREMENT", "LOGISTICS") if p in labels]
    team_data = {p: results(p, item, facility, geo) for p in teams}
    table_rows = []
    for metric in METRICS:
        picked = {p: card_row(team_data[p], metric, kind, month) for p in teams}
        shown = {p: value_text(metric, picked[p], gap(metric, team_data[p], kind, month) if picked[p] is None else None)
                 for p in teams}
        visible = {v for v in shown.values() if v != "Hidden for this role"}
        verdict = "Same for every team" if len(visible) <= 1 else "DIFFERENT — investigate"
        if len(visible) == 1 and len(set(shown.values())) > 1:
            verdict = "Same where visible; hidden by role"
        if all(picked[p] is None for p in teams):
            verdict = "Same for every team: nothing happened"
        table_rows.append({"Measure": METRICS[metric]["short"], **{labels[p].split(" — ")[-1]: shown[p] for p in teams}, "Check": verdict})
    show(st, pd.DataFrame(table_rows))
    st.caption("The full check across every published answer runs as real Snowflake roles in `scripts/verify.py personas`.")

    section("Trend", "Each point is the governed answer for one month. The dark line is what we know now; the light line is what we "
            "knew shortly after that month ended. A gap between them means late paperwork changed the answer.",
            "Final values against what was known shortly after each month ended.")
    t1, t2 = st.columns([1, 3])
    trend_options = [m for m in METRICS if m != "DAYS_INVENTORY"]
    trend_metric = t1.radio("Measure", trend_options, index=trend_options.index(default_metric(data, trend_options)),
                            format_func=lambda m: METRICS[m]["short"])
    trend = data[(data.RECENCY == 1) & (data.METRIC_ID == trend_metric)].copy()
    partial = pd.to_numeric(trend.DIAGNOSTIC_DISPLAY, errors="coerce")
    trend["Partial"] = trend.VALUE_NUM.isna() & (trend.STATUS == "INCOMPLETE") & partial.notna()
    trend = trend[trend.VALUE_NUM.notna() | trend.Partial]
    if trend.empty:
        t2.info(METRICS[trend_metric]["empty"])
    else:
        trend["Month"] = pd.to_datetime(trend.PERIOD_START)
        trend["Known"] = trend.AS_OF_KIND.map({"final": "Final", "early": "Early"})
        trend["Value"] = trend.VALUE_NUM.astype(float).where(~trend.Partial, partial.astype(float))
        trend["Status"] = trend.STATUS.map(lambda s: STATUS_LABEL.get(s, s))
        trend.loc[trend.Partial, "Status"] = "Not final: partial, known costs only"
        trend["Shown"] = trend.DISPLAY.where(~trend.Partial, trend.DIAGNOSTIC_DISPLAY)
        trend["Coverage"] = pd.to_numeric(trend.COVERAGE, errors="coerce").map(lambda c: f"{c:.1%}" if pd.notna(c) else "—")
        trend["Counted"] = trend.NUMERATOR.fillna("—")
        trend["Out of"] = trend.DENOMINATOR.fillna("—")
        axis = alt.Axis(format=".0%" if METRICS[trend_metric]["kind"] == "ratio" else "$,.2f", grid=True, gridColor="#EEF2F6")
        chart = (alt.Chart(trend).mark_line(point=alt.OverlayMarkDef(filled=True, size=55), strokeWidth=2.5)
                 .encode(x=alt.X("Month:T", axis=alt.Axis(format="%b %y", title=None)),
                         y=alt.Y("Value:Q", axis=axis, title=None, scale=alt.Scale(zero=False)),
                         color=alt.Color("Known:N", scale=alt.Scale(domain=["Final", "Early"], range=[BLUE, "#9FB3C8"]), legend=alt.Legend(orient="top")),
                         tooltip=["Known", alt.Tooltip("Month:T", format="%b %Y"), alt.Tooltip("Shown", title="Governed value"), "Status",
                                  "Counted", "Out of", alt.Tooltip("Coverage", title="Data coverage")])
                 .properties(height=280))
        hollow = (alt.Chart(trend[trend.Partial]).mark_point(filled=False, fill="white", size=90, strokeWidth=2, opacity=1)
                  .encode(x="Month:T", y="Value:Q", color=alt.Color("Known:N", legend=None)))
        t2.altair_chart(chart + hollow, use_container_width=True)
        if trend.Partial.any():
            t2.caption("Hollow points are not final: some duty, freight or other bills are still missing, so the governed value is "
                       "withheld. The point shows the cost per unit for the units whose bills are all in.")
        if METRICS[trend_metric]["kind"] == "ratio":
            sizes = pd.to_numeric(trend[trend.AS_OF_KIND == "final"].DENOMINATOR, errors="coerce").dropna()
            if not sizes.empty and sizes.median() < 20:
                t2.caption(f"Small sample: each month counts only {int(sizes.min())} to {int(sizes.max())} lines, so one late "
                           "delivery moves the percentage a lot. Widen the selection for a steadier trend.")

    section("Where it comes from", "The same measure split by region, site, supplier, customer or part. Every bar is a governed "
            "answer published by the database; the chart does no maths.")
    b1, b2 = st.columns([1, 3])
    b_metric = b1.radio("Measure ", trend_options, index=trend_options.index(trend_metric), format_func=lambda m: METRICS[m]["short"], key="bm")
    inbound_side = b_metric in ("INBOUND_SUPPLIER_OTD", "LANDED_COST_PER_ACCEPTED_UNIT")
    if item is None:
        dim_options = ["SUPPLIER", "FACILITY", "ITEM"] if inbound_side else ["GEOGRAPHY", "FACILITY", "CUSTOMER", "ITEM"]
    else:
        dim_options = ["FACILITY"] if inbound_side else ["GEOGRAPHY", "FACILITY"]
    dim = b1.radio("Split by", dim_options, format_func=lambda d: DIM_PLAIN[d])
    frame = breakdown(persona, b_metric, str(month), kind, dim, item)
    if frame.empty:
        b2.info(METRICS[b_metric]["empty"])
    else:
        frame["Name"] = frame.DIM_VALUE.map(lambda v: nice(dim, v))
        frame["Value"] = frame.VALUE_NUM.astype(float)
        frame["Status"] = frame.STATUS.map(lambda s: STATUS_LABEL.get(s, s))
        shown = frame[frame.Value.notna()].sort_values("Value").tail(15)
        if shown.empty:
            b2.info("Every row in this split is hidden or not final, so there is nothing to chart.")
            show(b2, frame[["Name", "Status", "COVERAGE"]].rename(columns={"COVERAGE": "Data coverage"}))
        else:
            bars = (alt.Chart(shown).mark_bar(cornerRadiusEnd=4, color=TEAL)
                    .encode(y=alt.Y("Name:N", sort="-x", title=None),
                            x=alt.X("Value:Q", title=None, axis=alt.Axis(format=".0%" if METRICS[b_metric]["kind"] == "ratio" else "$,.2f")),
                            tooltip=["Name", alt.Tooltip("DISPLAY", title="Governed value"), "Status",
                                     alt.Tooltip("NUMERATOR", title="Counted"), alt.Tooltip("DENOMINATOR", title="Out of")])
                    .properties(height=max(160, 26 * len(shown))))
            b2.altair_chart(bars, use_container_width=True)


def render_answer(entry: dict):
    result = entry["result"]
    route = result.get("route", "")
    st.markdown(f'<div class="answer"><div class="q">{esc(entry["persona_label"])} asked</div>'
                f'<div style="font-weight:650;font-size:1.05rem;margin-bottom:10px">{esc(entry["question"])}</div>', unsafe_allow_html=True)
    if route.startswith("ALIAS") or route == "CLARIFY":
        status = "REJECT" if route == "ALIAS_REJECT" else "CLARIFY"
        options = ", ".join(result.get("options") or [])
        st.markdown(f'{pill(status)} <div class="n" style="margin-top:8px">{esc(result.get("clarification") or "")}</div>'
                    f'<div class="kv" style="margin-top:8px">Governed options: <b>{esc(options or "none")}</b></div></div>', unsafe_allow_html=True)
        return
    env = result.get("envelope") or {}
    metric = env.get("metric_id")
    st.markdown(f'<div class="n">{esc(result.get("narration", ""))}</div>', unsafe_allow_html=True)
    cols = st.columns([1.1, 1.1, 2]) if result.get("compare") else st.columns([1.2, 2.8])
    row = {"STATUS": env.get("status"), "DISPLAY": env.get("display"), "PERCENT_DISPLAY": env.get("percent"), "NUMERATOR": env.get("numerator"),
           "DENOMINATOR": env.get("denominator"), "COVERAGE": env.get("coverage"), "REASONS": env.get("reasons"),
           "AFFECTED_COMMITMENTS": env.get("affected_commitments"), "DIAGNOSTIC_DISPLAY": env.get("diagnostic_display")}
    if metric in METRICS:
        cols[0].markdown(card(metric, row, f"as of {env.get('as_of')}"), unsafe_allow_html=True)
        if result.get("compare"):
            c = result["compare"]
            crow = {"STATUS": c.get("status"), "DISPLAY": c.get("display"), "PERCENT_DISPLAY": c.get("percent"), "NUMERATOR": c.get("numerator"),
                    "DENOMINATOR": c.get("denominator"), "COVERAGE": c.get("coverage"), "REASONS": c.get("reasons"),
                    "AFFECTED_COMMITMENTS": c.get("affected_commitments"), "DIAGNOSTIC_DISPLAY": c.get("diagnostic_display")}
            cols[1].markdown(card(metric, crow, f"compared: as of {c.get('as_of')} · period {' to '.join(c.get('period') or [])}"),
                             unsafe_allow_html=True)
    scope = ", ".join(f"{k}={v}" for k, v in (env.get("scope") or {}).items()) or "all"
    route_tip = ("Verified question: matched a question the data team approved in advance, with a fixed scope. "
                 "Model routed: the language model picked the measure and filters from a fixed menu, and the database checked them.")
    narration_tip = ("MODEL: the language model wrote the sentence and every number in it matched the database. "
                     "TEMPLATE: the model's wording failed that check, so a fixed sentence was used instead.")
    cols[-1].markdown(
        f'<div class="kv">How it was answered <b>{esc(route.replace("_", " ").title())}</b>{tip(esc(route_tip))} · wording '
        f'<b>{esc(result.get("narration_source", ""))}</b>{tip(esc(narration_tip))}'
        f'{" (" + esc(result["narration_note"]) + ")" if result.get("narration_note") else ""}<br>'
        f'Measure <b>{esc(env.get("display_name", metric))}</b> v{esc(env.get("metric_version", ""))}<br>'
        f'Period <b>{esc(" to ".join(env.get("period") or []))}</b> · as of <b>{esc(env.get("as_of", ""))}</b><br>'
        f'Scope <b>{esc(scope)}</b><br>'
        f'Evidence <b>{esc(env.get("evidence_id", ""))}</b> · {esc(env.get("evidence_count", 0))} records<br>'
        f'Definition fingerprint <b>{esc((env.get("definition_hash") or "")[:16])}…</b><br>Origin <b>{esc(env.get("origin", ""))}</b></div>',
        unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    with st.expander("Evidence envelope (the raw record behind this answer)"):
        st.json(env)
        if result.get("compare"):
            st.json(result["compare"])


SEMANTIC_VIEW = "CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY"
ANALYST_PATH = "/api/v2/cortex/analyst/message"


def analyst_call(messages: list) -> dict:
    body = {"messages": messages, "semantic_view": SEMANTIC_VIEW}
    try:
        import _snowflake  # available inside Streamlit in Snowflake

        resp = _snowflake.send_snow_api_request("POST", ANALYST_PATH, {}, {}, body, None, 50000)
        payload = json.loads(resp["content"]) if isinstance(resp.get("content"), str) else resp.get("content")
        if int(resp.get("status", 500)) >= 400:
            raise RuntimeError(f"Cortex Analyst returned {resp.get('status')}: {str(payload)[:300]}")
        return payload
    except ImportError:
        import requests

        conn = session().connection
        resp = requests.post(f"https://{conn.host}{ANALYST_PATH}", json=body, timeout=120,
                             headers={"Authorization": f'Snowflake Token="{conn.rest.token}"', "Content-Type": "application/json"})
        if resp.status_code >= 400:
            raise RuntimeError(f"Cortex Analyst returned {resp.status_code}: {resp.text[:300]}")
        return resp.json()


ACCEPTED = {"VERIFIED", "DESCRIPTIVE", "WITHHELD"}


def run_semantic(who: str, sql: str) -> dict:
    raw = session().sql("CALL CONCORDIA.APP.RUN_SEMANTIC_SQL(?, ?)", params=[who, sql]).collect()[0][0]
    return json.loads(raw)


def audit_semantic(who: str, question: str, answer: dict) -> None:
    run = answer.get("run") or {}
    if answer.get("fallback"):
        route = "SEMANTIC_VERIFIED_QUERY"
    elif answer.get("sql"):
        route = "CORTEX_ANALYST"
    elif answer.get("attempts"):
        route = "SEMANTIC_CLARIFY"
    else:
        route = "SEMANTIC_ALIAS"
    detail = json.dumps({"attempts": answer.get("attempts"), "fallback": answer.get("fallback"),
                         "row_count": run.get("row_count"), "reason": run.get("reason") or run.get("note"),
                         "cost_masked": run.get("cost_masked")}, default=str)
    sql, params = inline_nulls(
        "CALL CONCORDIA.APP.AUDIT_SEMANTIC(?, ?, ?, ?::VARCHAR, ?::VARCHAR, ?, ?)",
        [who, question, route, run.get("reason") or run.get("note"), answer.get("sql"),
         run.get("verdict") or "CLARIFY", detail])
    session().sql(sql, params=params).collect()


def verified_fallback(question: str):
    found = q("SELECT QUESTION, SQL_TEXT, FOLLOW_UP_ID FROM CONCORDIA.APP.ANALYST_VERIFIED "
              "WHERE JAROWINKLER_SIMILARITY(QUESTION, ?) >= 96 "
              "ORDER BY JAROWINKLER_SIMILARITY(QUESTION, ?) DESC LIMIT 1", [question, question])
    if found.empty:
        return None
    return found.iloc[0].QUESTION, found.iloc[0].SQL_TEXT, found.iloc[0].FOLLOW_UP_ID


def verified_exact(question: str):
    found = q("SELECT QUESTION, SQL_TEXT, FOLLOW_UP_ID FROM CONCORDIA.APP.ANALYST_VERIFIED "
              "WHERE LOWER(TRIM(QUESTION)) = LOWER(TRIM(?)) LIMIT 1", [question])
    if found.empty:
        return None
    return found.iloc[0].QUESTION, found.iloc[0].SQL_TEXT, found.iloc[0].FOLLOW_UP_ID


def follow_up(question_id, who: str):
    if not isinstance(question_id, str) or not question_id:
        return None
    found = q("SELECT QUESTION, SQL_TEXT FROM CONCORDIA.APP.ANALYST_VERIFIED WHERE QUESTION_ID = ?", [question_id])
    if found.empty:
        return None
    return {"question": found.iloc[0].QUESTION, "sql": found.iloc[0].SQL_TEXT, "run": run_semantic(who, found.iloc[0].SQL_TEXT)}


def governed_alias(question: str):
    normalized = question.lower()
    has_direction = re.search(r"\b(inbound|supplier|vendor|outbound|customer)\b", normalized)
    aliases = q("SELECT PHRASE, RESPONSE, OPTIONS, NOTE FROM CONCORDIA.APP.V_REJECTED_ALIAS")
    for row in aliases.itertuples(index=False):
        phrase = str(row.PHRASE).lower()
        if not re.search(r"\b" + re.escape(phrase) + r"\b", normalized):
            continue
        if phrase == "otd" and has_direction:
            continue
        if phrase == "cost" and "landed" in normalized:
            continue
        if phrase == "fill rate" and "unit fill rate" in normalized:
            continue
        return {"response": row.RESPONSE, "options": as_list(row.OPTIONS), "note": row.NOTE}
    return None


def analyst_answer(question: str, who: str) -> dict:
    messages = [{"role": "user", "content": [{"type": "text", "text": question}]}]
    out = {"text": "", "sql": None, "suggestions": [], "run": None, "attempts": 0, "fallback": None, "follow_up": None}
    exact = verified_exact(question)
    if exact:
        approved, sql, next_id = exact
        out.update({"text": "Using the steward-approved semantic query for this question.",
                    "sql": sql, "run": run_semantic(who, sql), "fallback": approved, "follow_up": follow_up(next_id, who)})
        return out
    alias = governed_alias(question)
    if alias:
        verdict = "CLARIFY" if alias["response"] == "CLARIFY" else "REJECT"
        out.update({"text": alias["note"], "suggestions": [],
                    "run": {"verdict": verdict, "reason": alias["note"], "rows": [], "columns": []}})
        return out
    content = []
    for _ in range(3):
        out["attempts"] += 1
        reply = analyst_call(messages)
        content = (reply.get("message") or {}).get("content") or []
        out["text"] = " ".join(p.get("text", "") for p in content if p.get("type") == "text").strip()
        out["suggestions"] = [s for p in content if p.get("type") == "suggestions" for s in p.get("suggestions", [])]
        out["sql"] = next((p.get("statement") for p in content if p.get("type") == "sql"), None)
        if not out["sql"]:
            out["run"] = {"verdict": "CLARIFY",
                          "reason": out["text"] or "Cortex Analyst did not identify one governed query.",
                          "rows": [], "columns": []}
            return out
        out["run"] = run_semantic(who, out["sql"])
        if out["run"].get("verdict") in ACCEPTED:
            return out
        messages += [{"role": "analyst", "content": content},
                     {"role": "user", "content": [{"type": "text", "text":
                      "That SQL was not accepted: " + str(out["run"].get("reason") or out["run"].get("note"))
                      + " Rewrite it as SELECT * FROM SEMANTIC_VIEW(...) and filter results.metric_id, results.scope_level, "
                        "results.known_as_of and results.month. Do not re-aggregate."}]}]
    match = verified_fallback(question)
    if match:
        approved, sql, next_id = match
        out["fallback"] = approved
        out["sql"] = sql
        out["run"] = run_semantic(who, sql)
        out["follow_up"] = follow_up(next_id, who)
        out["text"] = (out["text"] + " " if out["text"] else "") + "The generated query did not pass, so this is the approved query for that question."
    return out


COLUMN_PLAIN = {
    "METRIC_ID": "Measure", "MONTH": "Month", "STATUS": "Status", "GOVERNED_VALUE_TEXT": "Governed value", "PART_ID": "Part",
    "PART_NAME": "Part name", "SITE_NAME": "Site", "REGION_NAME": "Region", "SUPPLIER_NAME": "Supplier", "CUSTOMER_NAME": "Customer",
    "REASONS": "Why not final", "ORDER_LINE_ID": "Order line", "OUTCOME": "Result", "CAUSE_CODE": "Cause code", "CAUSE": "Cause",
    "DUE_ON": "Due", "COMPLETED_ON": "Completed", "MISSED_LINES": "Missed lines", "PO_LINE_ID": "PO line",
    "SUPPLIER_PROMISE_ON": "Supplier promised", "RECEIPT_ID": "Receipt", "RECEIVED_ON": "Received", "ACCEPTED_ON": "Accepted",
    "LOT_ID": "Lot", "RECEIVED_QTY": "Received qty", "SOURCE_SYSTEM": "System", "SOURCE_ITEM_KEY": "Their code",
}
ANSWER_CONTEXT = ("SCOPE_LEVEL", "KNOWN_AS_OF", "ACCESS_NOTE")
SCOPE_PLAIN = {"NETWORK": "Whole business", "PART": "One part, all sites and regions", "PART_SITE": "One part at one site",
               "PART_REGION": "One part in one customer region", "SITE": "One site", "REGION": "One customer region",
               "SUPPLIER": "One supplier", "CUSTOMER": "One customer"}
CLARIFY_REWRITES = [
    (r"\b(otif|on[- ]time in full)\b", None,
     [("Customer on-time delivery instead", "outbound customer OTD"), ("Unit fill rate instead", "unit fill rate")]),
    (r"\b(otd|on[- ]time delivery)\b", r"\b(inbound|supplier|vendor|outbound|customer)\b",
     [("Supplier on-time delivery (deliveries to us)", "inbound supplier OTD"),
      ("Customer on-time delivery (deliveries to customers)", "outbound customer OTD")]),
    (r"\bfill rate\b", r"\bunit fill rate\b", [("Unit fill rate (units shipped out of units ordered)", "unit fill rate")]),
    (r"\binventory days\b", None, [("Days of inventory", "days of inventory")]),
    (r"\bcost\b", r"\blanded cost\b", [("Landed cost per accepted unit", "landed cost per accepted unit")]),
]


def clarify_options(question: str) -> list[tuple[str, str]]:
    for pattern, skip, choices in CLARIFY_REWRITES:
        if re.search(pattern, question, re.I) and not (skip and re.search(skip, question, re.I)):
            return [(label, re.sub(pattern, phrase, question, count=1, flags=re.I)) for label, phrase in choices]
    return []


def cell_text(column: str, value):
    if blank(value):
        return MISSING
    if column == "METRIC_ID":
        return METRICS.get(value, {}).get("short", value)
    if column in ("STATUS", "OUTCOME"):
        return STATUS_LABEL.get(value) or DRIVER_PLAIN.get(value) or str(value).replace("_", " ").capitalize()
    if column == "MONTH":
        return month_label(value)
    if column == "REASONS":
        return ", ".join(plain_reason(r) for r in as_list(value)) or MISSING
    return value


def answer_view(run: dict) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    """Plain-language table, the shared context columns pulled out, and an optional trend frame."""
    raw = pd.DataFrame(run["rows"], columns=run["columns"])
    context = {}
    for column in ANSWER_CONTEXT:
        if column in raw.columns and raw[column].map(lambda v: MISSING if blank(v) else v).nunique() <= 1:
            values = [v for v in raw[column] if not blank(v)]
            context[column] = values[0] if values else None
            raw = raw.drop(columns=column)
    governed = [c for c in run.get("governed_columns") or [] if c in raw.columns]
    trend = None
    if governed and "MONTH" in raw.columns and raw.MONTH.nunique() >= 3:
        trend = pd.DataFrame({"Month": pd.to_datetime(raw.MONTH.map(iso_day), errors="coerce"),
                              "Value": pd.to_numeric(raw[governed[0]], errors="coerce"),
                              "Measure": raw.METRIC_ID.map(lambda m: METRICS.get(m, {}).get("short", m)) if "METRIC_ID" in raw else "Value",
                              "Shown": raw.GOVERNED_VALUE_TEXT if "GOVERNED_VALUE_TEXT" in raw else raw[governed[0]],
                              "Status": raw.STATUS.map(lambda s: STATUS_LABEL.get(s, s)) if "STATUS" in raw else ""}).dropna(subset=["Month", "Value"])
    if "GOVERNED_VALUE_TEXT" in raw.columns:
        raw = raw.drop(columns=[c for c in governed if c != "GOVERNED_VALUE_TEXT"])
    view = pd.DataFrame({COLUMN_PLAIN.get(c, c.replace("_", " ").capitalize()): raw[c].map(lambda v, c=c: cell_text(c, v))
                         for c in raw.columns})
    return view, context, trend


def headline_value(run: dict) -> str:
    """One governed answer: the value as the contract displays it, plus its percentage form for ratio measures."""
    if len(run.get("rows") or []) != 1:
        return ""
    row = dict(zip(run["columns"], run["rows"][0]))
    metric, shown = row.get("METRIC_ID"), row.get("GOVERNED_VALUE_TEXT")
    if metric not in METRICS or blank(shown):
        return ""
    kind = METRICS[metric]["kind"]
    try:
        big = f"{float(shown):.1%}" if kind == "ratio" else (f"${shown}" if kind == "usd" else f"{trim(shown)} days")
    except ValueError:
        big = str(shown)
    where = " · ".join(str(row[c]) for c in ("PART_ID", "SITE_NAME", "REGION_NAME", "SUPPLIER_NAME", "CUSTOMER_NAME") if not blank(row.get(c)))
    return (f'<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:10px 0 2px 0">'
            f'<div class="card" style="min-height:0;padding:12px 18px;flex:0 0 auto"><div class="team">{esc(METRICS[metric]["short"])}</div>'
            f'<div class="value" style="margin:4px 0 0 0">{esc(big)}</div>'
            f'<div class="meta">{esc(month_label(row.get("MONTH")))}{" · " + esc(where) if where else ""} · governed value {esc(shown)}</div></div>'
            f'{pill(row.get("STATUS")) if row.get("STATUS") else ""}</div>')


def ask_again(question: str):
    # Runs as a button callback, before the page reads the pending question on the next run.
    st.session_state.pending = question


def run_metric_ids(run: dict) -> set:
    if "METRIC_ID" not in (run.get("columns") or []):
        return set()
    index = run["columns"].index("METRIC_ID")
    return {r[index] for r in run.get("rows") or [] if not blank(r[index])}


def answer_route(a: dict) -> str:
    if a.get("error"):
        return '<span class="chip warn">Cortex Analyst unavailable</span>'
    if a.get("fallback"):
        return '<span class="chip ok">Approved question · steward-written query, no AI needed</span>'
    if a.get("sql"):
        return '<span class="chip">Cortex Analyst wrote the query · guard checked it</span>'
    if a.get("attempts"):
        return '<span class="chip">Cortex Analyst needs more detail</span>'
    return '<span class="chip warn">Governed vocabulary rule</span>'


def render_analyst(entry: dict):
    a = entry["analyst"]
    run = a.get("run") or {}
    verdict = run.get("verdict")
    detail = run.get("reason") or run.get("note") or ""
    text = a.get("text") or ""
    st.markdown(f'<div class="answer"><div class="q">{esc(entry["persona_label"])} asked</div>'
                f'<div style="font-weight:650;font-size:1.05rem;margin-bottom:8px">{esc(entry["question"])}</div>'
                f'{answer_route(a)}{pill(verdict) if verdict else pill("REJECTED" if a.get("error") else "CLARIFY")}'
                f'{headline_value(run) if verdict == "VERIFIED" else ""}'
                f'<div class="n" style="margin-top:8px">{esc(text)}</div>'
                f'{"<div class=kv>" + esc(detail) + "</div>" if detail and detail.strip() != text.strip() else ""}</div>',
                unsafe_allow_html=True)
    if verdict in ("CLARIFY", "REJECT", "REJECTED") and not run.get("sql"):
        options = clarify_options(entry["question"])
        if options:
            st.caption("Pick what you meant and Concordia will ask again. Governed measures are always shown separately, "
                       "never blended into one number.")
            cols = st.columns(len(options))
            for i, (label, rewritten) in enumerate(options):
                cols[i].button(label, key=f"clar{entry['id']}_{i}", use_container_width=True, help=rewritten,
                               on_click=ask_again, args=(rewritten,))
    if verdict in ("VERIFIED", "DESCRIPTIVE") and run.get("rows"):
        view, context, trend = answer_view(run)
        if trend is not None and not trend.empty:
            ids = run_metric_ids(run)
            ratio = bool(ids) and all(METRICS.get(m, {}).get("kind") == "ratio" for m in ids)
            st.altair_chart(
                alt.Chart(trend).mark_line(point=alt.OverlayMarkDef(filled=True, size=50), strokeWidth=2.5)
                .encode(x=alt.X("Month:T", axis=alt.Axis(format="%b %y", title=None)),
                        y=alt.Y("Value:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(format=".0%" if ratio else ",.2f")),
                        color=alt.Color("Measure:N", legend=alt.Legend(orient="top", title=None)),
                        tooltip=["Measure", alt.Tooltip("Month:T", format="%b %Y"), alt.Tooltip("Shown", title="Governed value"), "Status"])
                .properties(height=240), use_container_width=True)
        show(st, view)
        notes = []
        if context.get("SCOPE_LEVEL"):
            notes.append("Scope: " + SCOPE_PLAIN.get(context["SCOPE_LEVEL"], str(context["SCOPE_LEVEL"])))
        if context.get("KNOWN_AS_OF"):
            notes.append("Known as of: " + ("today (final)" if context["KNOWN_AS_OF"] == "final" else "5th of the next month (early)"))
        if context.get("ACCESS_NOTE"):
            notes.append(str(context["ACCESS_NOTE"]))
        if notes:
            st.caption(" · ".join(notes))
    elif verdict in ("VERIFIED", "DESCRIPTIVE"):
        st.info("The query ran, but nothing was published for that exact selection: no orders, receipts or stock were recorded "
                "there. Try a wider scope (the whole part instead of one region) or a different month.")
    extra = a.get("follow_up") or {}
    extra_run = extra.get("run") or {}
    if extra_run.get("verdict") in ("VERIFIED", "DESCRIPTIVE"):
        st.markdown(f'<div class="section">{esc(extra["question"])}</div><div class="sub">The order lines stored with the published '
                    'answer, with the cause recorded for each miss. Same publish run, so they add up to the numbers above.</div>',
                    unsafe_allow_html=True)
        if extra_run.get("rows"):
            show(st, answer_view(extra_run)[0])
        else:
            st.info("No order lines match for this persona.")
        with st.expander("The approved follow-up query"):
            st.code(extra.get("sql") or "", language="sql")
    for i, text in enumerate(a.get("suggestions") or []):
        st.button(text, key=f"sug{entry['id']}_{i}", use_container_width=True, on_click=ask_again, args=(text,))
    if a.get("sql"):
        with st.expander("The SQL Cortex Analyst wrote, and what the guard checked"):
            st.code(a["sql"], language="sql")
            st.caption(f"Attempts: {a.get('attempts')} · scope rows checked: {run.get('checked_values', 0)}"
                       f"{' · approved query used' if a.get('fallback') else ''}"
                       f"{' · landed cost hidden by the masking policy' if run.get('cost_masked') else ''}")
    if a.get("error"):
        with st.expander("Technical details"):
            st.code(a["error"][:4000])
    if a.get("audit_error"):
        st.error("The answer ran, but its audit record could not be written. Treat this response as incomplete.")


FREE_FORM = [
    "Supplier on-time delivery for CP-1019 in March 2026",
    "Customer on-time delivery for MM-401 in January 2026",
    "What was inbound OTD at Reno in February 2026?",
    "Unit fill rate by region for March 2026",
    "Show customer OTD trend for MM-440",
    "Which suppliers deliver late most often?",
]


def page_ask():
    intro("Ask Concordia", "Type a question the way you would ask a colleague.",
          "The primary answer path is Snowflake Cortex Analyst over the governed supply-chain semantic view. A guard runs only "
          "read-only ontology queries, refuses re-averaging, and accepts a number only when it equals the published answer for that "
          "metric, month and scope. A Snowflake masking policy hides landed cost from personas who may not see it. Approved questions "
          "are stored on the semantic view and provide a deterministic fallback. Use Metric evidence envelope when you want the "
          "underlying single-metric record and evidence identifiers.")
    st.session_state.setdefault("chat", [])
    engine = st.radio(
        "Answer mode",
        ["Governed semantic answer", "Metric evidence envelope"],
        horizontal=True,
        key="answer_mode_v2",
        help="Governed semantic answer is the primary path: Cortex Analyst reads the supply-chain ontology and can combine "
             "metrics and relationships. Metric evidence envelope is the deterministic drill-down for one metric.",
    )
    analyst_mode = engine == "Governed semantic answer"
    if analyst_mode:
        groups = [
            ("Free-form: Cortex Analyst writes the query", FREE_FORM),
            ("Approved questions: the data team wrote the query in advance", list(D["questions"].QUESTION)),
            ("Words Concordia clarifies or refuses", ["What was OTD last May?", "What is our OTIF for May 2026?"]),
        ]
    else:
        envelope = D["questions"][D["questions"].METRIC_ID.notna()]
        groups = [("Single-metric evidence questions", list(envelope.QUESTION)),
                  ("Words Concordia clarifies or refuses", ["What was OTD last month?", "What is our OTIF for May 2026?"])]
    with st.expander("Questions to try", expanded=not st.session_state.chat):
        for g, (title, texts) in enumerate(groups):
            st.markdown(f'<div class="sub" style="margin:6px 0 4px 0"><b>{esc(title)}</b></div>', unsafe_allow_html=True)
            grid = st.columns(3)
            for i, text in enumerate(texts):
                grid[i % 3].button(text, key=f"vq{int(analyst_mode)}_{g}_{i}", use_container_width=True, on_click=ask_again, args=(text,))
    asked = st.chat_input("Ask about supplier on-time delivery, customer on-time delivery, fill rate, days of inventory or landed cost…")
    question = asked or st.session_state.pop("pending", None)
    if question:
        entry = {"id": len(st.session_state.chat), "question": question, "persona_label": labels[persona]}
        if analyst_mode:
            with st.spinner("Cortex Analyst is reading the semantic view → guard checks the SQL → Snowflake runs it"):
                try:
                    entry["analyst"] = analyst_answer(question, persona)
                except Exception as exc:  # noqa: BLE001 - surface service errors instead of failing the page
                    entry["analyst"] = {"text": "Cortex Analyst could not answer just now. Ask again, or pick an approved question "
                                                "from the list above.", "run": None, "error": str(exc)}
                else:
                    try:
                        audit_semantic(persona, question, entry["analyst"])
                    except Exception as exc:  # noqa: BLE001 - preserve the answer and disclose an audit write failure
                        entry["analyst"]["audit_error"] = str(exc)
        else:
            with st.spinner("Understanding the question → calculating in Snowflake → attaching evidence → wording the answer"):
                raw = session().sql("CALL CONCORDIA.APP.ASK(?, ?)", params=[persona, question]).collect()[0][0]
            entry["result"] = json.loads(raw)
        st.session_state.chat.insert(0, entry)
    if st.session_state.chat:
        st.button("Clear answers", key="clear_chat", on_click=lambda: st.session_state.update(chat=[]))
    for entry in st.session_state.chat:
        if "analyst" in entry:
            render_analyst(entry)
        else:
            render_answer(entry)
        st.write("")


def page_bridge():
    intro("Why it changed", "This month against last month: what went wrong, and on which orders?",
          "Every order line that missed or was left out has a cause. The chart counts causes; the table lists the actual lines.")
    if len(MONTHS) < 2:
        st.info("Needs at least two published months.")
        return
    c1, c2, c3 = st.columns(3)
    options = ["OUTBOUND_CUSTOMER_OTD", "INBOUND_SUPPLIER_OTD", "UNIT_FILL_RATE"]
    item = focus_item
    metric = c1.selectbox("Measure", options, index=options.index(default_metric(results(persona, item), options)),
                          format_func=lambda m: METRICS[m]["short"],
                          help="Customer on-time is about deliveries to customers; supplier on-time is about deliveries to us.")
    flow = [m for m in FLOW_MONTHS if m in MONTHS]
    month = month_picker(c2, "bridge_month", flow[1:] or MONTHS[1:])
    geo = None
    if metric != "INBOUND_SUPPLIER_OTD":
        geo_options = [None] + list(D["geos"].GEOGRAPHY_ID)
        lead_geo = question_scope(metric, "PRIOR_PERIOD").get("geography_id") if item == LEAD_SCOPE.get("item_id") else None
        by_region = breakdown(persona, metric, str(month), "final", "GEOGRAPHY", item)
        active = set(by_region.DIM_VALUE) if not by_region.empty else set()

        def region_label(g):
            if g is None:
                return "All regions"
            return GEO_NAMES.get(g, g) + ("" if g in active else f" · no orders in {month_label(month)}")

        geo = c3.selectbox("Customer region", geo_options, index=geo_options.index(lead_geo) if lead_geo in geo_options else 0,
                           format_func=region_label,
                           help="Where the customer is. Regions marked 'no orders' had no customer order lines due that month "
                                "for this part, so there is nothing to score there.")
    choices = flow or MONTHS
    prior = choices[choices.index(month) - 1] if month in choices and choices.index(month) > 0 else MONTHS[MONTHS.index(month) - 1]
    data = results(persona, item, None, geo)
    scoped = data[(data.RECENCY == 1) & (data.AS_OF_KIND == "final")]
    now = pick(scoped[in_month(scoped.PERIOD_START, month)], METRIC_ID=metric)
    before = pick(scoped[in_month(scoped.PERIOD_START, prior)], METRIC_ID=metric)
    now_gap = gap(metric, data, "final", month) if now is None else None
    before_gap = gap(metric, data, "final", prior) if before is None else None
    st.markdown(f'<div class="section">{esc(item_label(item))}{" · " + esc(GEO_NAMES.get(geo, "")) if geo else ""}</div>', unsafe_allow_html=True)
    a, b, c = st.columns([1, 1, 2])
    a.markdown(card(metric, before, title=f"{METRICS[metric]['short']} · {month_label(prior)}", info=before_gap), unsafe_allow_html=True)
    b.markdown(card(metric, now, title=f"{METRICS[metric]['short']} · {month_label(month)}", info=now_gap), unsafe_allow_html=True)
    jump_buttons(b, now_gap, "bridge_now")
    lines = q("SELECT * FROM TABLE(CONCORDIA.APP.CONTRIBUTION_FOR(?, ?, ?::DATE, ?::DATE, ?::VARCHAR, ?::VARCHAR)) LIMIT 5000",
              [persona, metric, str(prior), str(month), item, geo])
    if lines.empty:
        c.info((now_gap or before_gap or {}).get("why") or METRICS[metric]["empty"])
        return
    lines["Month"] = lines.PERIOD_START.map(month_label)
    drivers = lines[lines.OUTCOME.isin(["MISS", "EXCLUDED"])].copy()
    drivers["Cause"] = drivers.DRIVER.fillna(drivers.OUTCOME).map(plain_driver)
    counts = drivers.groupby(["Month", "Cause"]).size().reset_index(name="Lines")
    with c:
        section("Causes of misses", "Each bar counts order lines that missed (or were left out because their data could not be "
                "trusted), grouped by cause, for the two months.")
    if counts.empty:
        c.success("No misses or exclusions in either month.")
    else:
        chart = (alt.Chart(counts).mark_bar(cornerRadiusEnd=3)
                 .encode(y=alt.Y("Cause:N", title=None, sort="-x", axis=alt.Axis(labelLimit=260)),
                         x=alt.X("Lines:Q", title="Order lines", axis=alt.Axis(format="d", tickMinStep=1)),
                         color=alt.Color("Month:N", scale=alt.Scale(range=["#9FB3C8", BLUE]), legend=alt.Legend(orient="top")),
                         yOffset="Month:N", tooltip=["Month", "Cause", "Lines"])
                 .properties(height=max(180, 46 * counts.Cause.nunique())))
        c.altair_chart(chart, use_container_width=True)
    section("The actual order lines", f"Every line counted in {month_label(month)}. On time and complete, missed, or left out, "
            "with the cause and the dates.")
    view = lines[in_month(lines.PERIOD_START, month)].copy()
    if view.empty:
        st.info(f"No order lines were due in {month_label(month)} for this selection. The lines for {month_label(prior)} are "
                "counted in the left card.")
        return
    view["Result"] = view.OUTCOME.map(plain_driver)
    view["Cause"] = view.DRIVER.map(plain_driver)
    view["Why left out"] = view.REASONS.map(lambda r: ", ".join(plain_reason(x) for x in as_list(r)) or "—")
    view["Site"] = view.FACILITY_ID.map(lambda f: FAC_NAMES.get(f, f))
    view["Region"] = view.GEOGRAPHY_ID.map(lambda g: GEO_NAMES.get(g, g) if isinstance(g, str) else "—")
    view["Customer / supplier"] = [PARTY_NAMES.get(cu if isinstance(cu, str) else su, cu if isinstance(cu, str) else su)
                                   for cu, su in zip(view.CUSTOMER_ID, view.SUPPLIER_ID)]
    view["COMPLETED_ON"] = view.COMPLETED_ON.map(lambda v: "Not yet" if blank(v) else v)
    show(st, view[["LINE_ID", "ITEM_ID", "Site", "Region", "Customer / supplier", "Result", "Cause", "COMMITMENT_ON", "COMPLETED_ON",
                   "QTY", "Why left out"]]
         .rename(columns={"LINE_ID": "Order line", "ITEM_ID": "Part", "COMMITMENT_ON": "Promised for", "COMPLETED_ON": "Completed on",
                          "QTY": "Quantity"})
         .sort_values(["Result", "Order line"]), height=320)


def page_asof():
    intro("As-of replay", "What did we know, and when? How does late paperwork change an answer?",
          "The same question can have a different, correct answer depending on what had arrived by then. Nothing is overwritten: "
          "both answers are kept.")
    if not MONTHS:
        st.info("No published periods yet.")
        return
    c1, c2 = st.columns(2)
    month = month_picker(c1, "asof_month")
    item = focus_item
    early_rec = receipts(persona, str(month), "early", item, None)
    final_rec = receipts(persona, str(month), "final", item, None)
    sites = sorted(set(early_rec.FACILITY_ID.dropna()) | set(final_rec.FACILITY_ID.dropna()))
    metric = "LANDED_COST_PER_ACCEPTED_UNIT"
    section(f"Landed cost per unit · {item_label(item)} · {month_label(month)}",
            "Landed cost needs every bill: supplier invoice, freight, duty, insurance and broker. Early on, some bills have not "
            "arrived, so the answer is 'not final'. Once they arrive, the true cost appears.")
    if item is not None and not sites:
        st.info(f"{METRICS[metric]['empty']} No goods were received for {item} in {month_label(month)}.")
    else:
        lead_site = question_scope(metric, "EARLY_AS_OF").get("facility_id")
        site_options = [None] + sites if item is None else sites
        site = c2.selectbox("Receiving site", site_options, index=site_options.index(lead_site) if lead_site in site_options else 0,
                            format_func=lambda f: "All sites" if f is None else FAC_NAMES.get(f, f),
                            help="The factory or warehouse that received the goods.")
        data = results(persona, item, site)
        early = pick(data[(data.RECENCY == 1) & in_month(data.PERIOD_START, month)], METRIC_ID=metric, AS_OF_KIND="early")
        final = pick(data[(data.RECENCY == 1) & in_month(data.PERIOD_START, month)], METRIC_ID=metric, AS_OF_KIND="final")
        early_day = early_as_of(data, month)
        a, b, c = st.columns([1, 1, 2])
        a.markdown(card(metric, early, title=f"As known {early_day}"), unsafe_allow_html=True)
        b.markdown(card(metric, final, title=f"As known {FINAL_AS_OF}"), unsafe_allow_html=True)
        rec = pd.concat([early_rec.assign(Known=early_day), final_rec.assign(Known=FINAL_AS_OF)])
        if site is not None:
            rec = rec[rec.FACILITY_ID == site]
        with c:
            section("The deliveries behind it", "Each goods receipt counted in this landed cost, on each date. 'Bills complete' "
                    "says whether every cost document had arrived.")
        if rec.empty:
            c.info("No goods receipts for this selection.")
        else:
            rec["Missing"] = rec.GAPS.map(lambda g: ", ".join(plain_reason(x) for x in as_list(g)) or "—")
            rec["Bills complete"] = rec.COVERED.map(lambda v: "Yes" if v else "No")
            show(c, rec[["Known", "RECEIPT_ID", "ACCEPTED_QTY", "Bills complete", "Missing", "LANDED_USD", "FREIGHT_USD"]]
                 .rename(columns={"RECEIPT_ID": "Receipt", "ACCEPTED_QTY": "Units accepted", "LANDED_USD": "Landed cost (USD)",
                                  "FREIGHT_USD": "Freight share (USD)"}), height=260)
            if bool(rec.MASKED.any()):
                c.caption("Cost columns are hidden for your role by the database (APP.RECEIPTS_FOR).")

    section("Answers changed by the latest data load", "When the second batch of data arrived, some answers changed. These are "
            "every answer whose value or status moved between the last two loads, for the scope you choose.")
    runs = publish_runs()
    if len(runs) < 2:
        st.info("Only one data load so far. Loading the second batch will show changed answers here.")
    else:
        scope = st.radio("Scope", ["Whole business", "Focus part"], horizontal=True,
                         help="Whole business = all parts, sites and regions together.")
        everything = results(persona, item if scope == "Focus part" else None)
        keys = ["METRIC_ID", "AS_OF_KIND", "PERIOD_START"]
        cur = everything[everything.RECENCY == 1].set_index(keys)
        old = everything[everything.RECENCY == 2].set_index(keys)
        joined = cur[["STATUS", "DISPLAY"]].join(old[["STATUS", "DISPLAY"]], rsuffix="_BEFORE", how="inner")
        changed = joined[(joined.STATUS != joined.STATUS_BEFORE) | (joined.DISPLAY.fillna("") != joined.DISPLAY_BEFORE.fillna(""))].reset_index()
        if changed.empty:
            st.success("Nothing changed for this scope between the last two loads.")
        else:
            changed["Measure"] = changed.METRIC_ID.map(lambda m: METRICS[m]["short"])
            changed["Month"] = changed.PERIOD_START.map(month_label)
            changed["Known"] = changed.AS_OF_KIND.map({"final": "Final", "early": "Early"})
            changed["Before"] = [f"{STATUS_LABEL.get(s, s)} {d}" if isinstance(d, str) else STATUS_LABEL.get(s, s)
                                 for s, d in zip(changed.STATUS_BEFORE, changed.DISPLAY_BEFORE)]
            changed["After"] = [f"{STATUS_LABEL.get(s, s)} {d}" if isinstance(d, str) else STATUS_LABEL.get(s, s)
                                for s, d in zip(changed.STATUS, changed.DISPLAY)]
            show(st, changed[["Measure", "Month", "Known", "Before", "After"]], height=300)
    section("Data loads", "Every load, matching and publishing step, with when it ran and how many rows it handled.")
    pipeline = table("V_PIPELINE", "ORDER BY STARTED_AT DESC", limit=30)
    show(st, pipeline[["STARTED_AT", "STEP", "STATUS", "ROWS_IN", "ROWS_OUT"]]
         .rename(columns={"STARTED_AT": "Started", "STEP": "Step", "STATUS": "Status", "ROWS_IN": "Rows in", "ROWS_OUT": "Rows out"}),
         height=260)


EDGE_PLAIN = {
    "SUPPLIES": "supplies", "COMPONENT_OF": "is a component of", "CAPABLE_OF_PRODUCING": "can make", "RECEIVED_FROM": "received from",
    "HELD_AT": "held at", "FULFILLS": "fulfils", "EXECUTED_AT": "made at", "PRODUCES": "produces", "PLACED": "placed",
    "DELIVERED_TO": "delivered to", "PROMISES": "promises", "COST_OF": "cost of", "RETURNED_AGAINST": "returned against",
    "FEEDBACK_ON": "feedback on", "SAME_AS": "same as", "CONSUMES": "consumes", "SUBSTITUTES_FOR": "substitutes for",
    "PARENT_OF": "parent of", "BELONGS_TO_FAMILY": "belongs to family", "IN_COUNTRY": "in country",
    "IN_REGION": "in region", "CONTAINS": "contains lot", "SENSES": "senses", "ALLOCATED_TO": "allocated to",
}
EDGE_HELP = {
    "SUPPLIES": "This supplier sells us the part.",
    "COMPONENT_OF": "This part is built into the other one (bill of materials).",
    "CAPABLE_OF_PRODUCING": "This factory is set up to make the part.",
    "RECEIVED_FROM": "Goods were received from this supplier.",
    "HELD_AT": "Stock of the part sits at this site.",
    "FULFILLS": "This shipment or receipt fulfils the order.",
    "EXECUTED_AT": "The work happened at this site.",
    "PRODUCES": "This production run made the part.",
    "PLACED": "This customer placed the order.",
    "DELIVERED_TO": "The goods went to this customer location.",
    "PROMISES": "The promise date given to the customer for this order.",
    "COST_OF": "A bill (invoice, freight, duty) that belongs to this receipt.",
    "RETURNED_AGAINST": "A customer return booked against this order.",
    "FEEDBACK_ON": "A customer rating or complaint about this order.",
    "SAME_AS": "Two codes from different systems that are the same part, company or site.",
    "CONSUMES": "Making the parent uses up this component.",
    "SUBSTITUTES_FOR": "An approved replacement part.",
    "PARENT_OF": "The parent in the product structure.",
    "BELONGS_TO_FAMILY": "The product family the part belongs to.",
    "IN_COUNTRY": "The country the site or company is in.",
    "IN_REGION": "The customer region.",
    "CONTAINS": "A physical lot (batch) carried by this receipt or shipment.",
    "SENSES": "A dock sensor reading that recorded this lot.",
    "ALLOCATED_TO": "This lot was assigned to a customer shipment.",
}


def page_graph():
    intro("One graph", "How do the six systems' records join up into one picture of a part?",
          "Every system has its own code for the same part, supplier or site. Concordia matches them to one identity and links "
          "them: who supplies the part, where it is made, which orders use it.")
    item = focus_item
    if item is None:
        st.info("Choose a part in the Focus box on the left to see its connections.")
    else:
        node = f"PART:{item}"
        edges = table("V_KG_EDGE", "WHERE SRC_ID = ? OR DST_ID = ?", (node, node), limit=200)
        dot = ['digraph G { rankdir=LR; bgcolor="transparent"; node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 '
               f'color="{LINE}" fillcolor="#FFFFFF" fontcolor="{NAVY}"]; edge [fontname="Helvetica" fontsize=9 color="#9FB3C8" fontcolor="{SLATE}"];',
               f'"{node}" [label="{item}\\n{ITEM_NAMES.get(item, "")}" fillcolor="{NAVY}" fontcolor="white" color="{NAVY}"];']
        colors = {"PARTY": "#E6F6F4", "FAC": "#EAF0FD", "PART": "#F1F4F8", "RCPT": "#FFF8EB", "PO": "#FDF3E1"}

        def label(node_id: str) -> str:
            _, _, key = node_id.partition(":")
            name = PARTY_NAMES.get(key) or FAC_NAMES.get(key) or ITEM_NAMES.get(key) or ""
            return f"{key}\\n{name}" if name else key

        shown = edges.head(28)
        for e in shown.itertuples():
            for n in (e.SRC_ID, e.DST_ID):
                if n != node:
                    dot.append(f'"{n}" [label="{label(n)}" fillcolor="{colors.get(n.split(":")[0], "#FFFFFF")}"];')
            dot.append(f'"{e.SRC_ID}" -> "{e.DST_ID}" [label="{EDGE_PLAIN.get(e.EDGE_TYPE, e.EDGE_TYPE.lower())}"];')
        dot.append("}")
        g1, g2 = st.columns([3, 2])
        with g1:
            section(f"Connections of {item}", "Boxes are things (parts, companies, sites, orders, receipts); arrows are relationships "
                    "recorded in the source systems. Green = company, blue = site, grey = part, amber = order or receipt.")
        g1.graphviz_chart("\n".join(dot), use_container_width=True)
        if edges.empty:
            g1.info("No recorded connections for this part.")
        aliases = table("V_ALIAS", "WHERE CANONICAL_ID = ? ORDER BY SOURCE_SYSTEM", (item,), limit=50)
        with g2:
            section("What each system calls it", "The code each source system uses for this part, and how Concordia matched it. "
                    "Exact key = same code; GTIN = matched on the barcode number; administered = mapped by the data team.")
        show(g2, aliases[["SOURCE_SYSTEM", "SOURCE_KEY", "METHOD"]]
             .rename(columns={"SOURCE_SYSTEM": "System", "SOURCE_KEY": "Their code", "METHOD": "How matched"}), height=240)
        codes = ", ".join(f"<code>{esc(k)}</code> in {esc(s)}" for s, k in zip(aliases.SOURCE_SYSTEM, aliases.SOURCE_KEY)) or "its own code"
        g2.markdown(
            f'<div class="explain"><div class="k">What "same as" means</div>'
            f'Each system names the same physical part differently: {codes}. A <b>SAME_AS</b> link says '
            f'"these codes are one part, <b>{esc(item)}</b>". Without it, an order from one system and a receipt from another '
            f'would look like two unrelated parts, and the numbers would not add up. With it, every system\'s records count toward '
            f'one part, so every team gets the same answer.</div>', unsafe_allow_html=True)
        g2.caption(f"{len(edges)} connections touch this part{'; showing 28' if len(edges) > 28 else ''}.")
        present_types = sorted(set(shown.EDGE_TYPE)) if not shown.empty else []
        if present_types:
            g1.markdown(" ".join(f'<span class="chip" title="{esc(EDGE_HELP.get(t, ""))}">{esc(EDGE_PLAIN.get(t, t.lower()))}</span>'
                                 for t in present_types), unsafe_allow_html=True)
            with g1.expander("What each arrow means"):
                show(st, pd.DataFrame([{"Arrow": EDGE_PLAIN.get(t, t.lower()), "Meaning": EDGE_HELP.get(t, "A recorded relationship.")}
                                       for t in present_types]))

    section("Data the measures refuse to hide", "Records Concordia could not trust are set aside rather than silently fixed, and "
            "you can see them here.")
    q1, q2, q3 = st.columns(3)
    quarantine = table("V_QUARANTINE", limit=5000)
    if not quarantine.empty:
        qc = quarantine.groupby("REASON").size().reset_index(name="Records").sort_values("Records")
        qc["Reason"] = qc.REASON.map(plain_reason)
        q1.markdown("**Records set aside**")
        q1.altair_chart(alt.Chart(qc).mark_bar(color=AMBER, cornerRadiusEnd=3)
                        .encode(y=alt.Y("Reason:N", title=None, sort="-x"), x=alt.X("Records:Q", title=None), tooltip=["Reason", "Records"])
                        .properties(height=max(140, 28 * len(qc))), use_container_width=True)
    resolution = table("V_RESOLUTION", limit=5000)
    q2.markdown("**Matches still to confirm**")
    if resolution.empty:
        q2.info("None open.")
    else:
        show(q2, resolution[["SOURCE_SYSTEM", "SOURCE_KEY", "CANDIDATE_ID", "METHOD", "SCORE", "STATUS"]].head(200)
             .rename(columns={"SOURCE_SYSTEM": "System", "SOURCE_KEY": "Their code", "CANDIDATE_ID": "Possible match",
                              "METHOD": "How", "SCORE": "Score", "STATUS": "Status"}), height=260)
    sources = table("V_SOURCE_COUNTS", "ORDER BY SOURCE_SYSTEM, SOURCE_OBJECT", limit=200)
    q3.markdown("**Records received from each system**")
    by_system = sources.groupby("SOURCE_SYSTEM").RECORDS.sum().reset_index()
    q3.altair_chart(alt.Chart(by_system).mark_arc(innerRadius=55)
                    .encode(theta="RECORDS:Q", color=alt.Color("SOURCE_SYSTEM:N", scale=alt.Scale(range=[NAVY, BLUE, TEAL, "#2F6FED", "#9FB3C8"]),
                                                                legend=alt.Legend(orient="bottom", title=None)),
                            tooltip=["SOURCE_SYSTEM", "RECORDS"]).properties(height=240), use_container_width=True)
    q3.caption("ERP = orders and invoices · MES = factory production · WMS = warehouse stock · TMS = shipping · CRM = customer promises.")
    conflicts = table("V_PROMISE_CONFLICT", limit=5000)
    st.caption(f"{len(conflicts):,} customer order lines where the order system and the customer system disagree on the promised date. "
               "Customer on-time delivery always uses the original promise, so both teams see the same number.")


def page_governance():
    intro("Governance", "Who decided what each number means, who may see what, and what has been asked?",
          "Each measure is written down once, versioned and fingerprinted. Every answer leaves evidence and every question is logged.")
    tabs = st.tabs(["Measure definitions", "Words we clarify or refuse", "Who can see what", "Questions asked", "Evidence", "Where data comes from"])
    with tabs[0]:
        st.caption("The written contract behind each measure. The fingerprint changes if anyone edits the definition.")
        contracts = table("V_CONTRACT", "ORDER BY METRIC_ID")
        for r in contracts.itertuples():
            with st.expander(f"{METRICS.get(r.METRIC_ID, {}).get('short', r.DISPLAY_NAME)} · version {r.METRIC_VERSION} · {r.STATUS}"):
                st.markdown(f"**In plain words.** {METRICS.get(r.METRIC_ID, {}).get('question', '')}\n\n"
                            f"**Formal question.** {r.QUESTION}\n\n**Period clock.** {r.PERIOD_CLOCK}\n\n**Counted.** {r.NUMERATOR_DEF}\n\n"
                            f"**Out of.** {r.DENOMINATOR_DEF}\n\n**Owner.** {r.OWNER} · **Approver.** {r.APPROVER}\n\n"
                            f"**Calculated by.** `{r.RESULT_FUNCTION}` · **Fingerprint.** `{r.DEFINITION_HASH}`")
    with tabs[1]:
        st.caption("Words that mean different things to different teams. Concordia asks which one you mean, or says it has no agreed definition.")
        show(st, table("V_REJECTED_ALIAS"))
    with tabs[2]:
        who = roster.assign(Sites=roster.ALLOWED_FACILITIES.map(site_list)).drop(columns=["ALLOWED_FACILITIES"])
        show(st, who.rename(columns={"PERSONA": "Role", "DISPLAY_NAME": "Name", "TITLE": "Title", "COST_VISIBLE": "Sees cost",
                                     "AUDIT_VISIBLE": "Sees everyone's questions"}))
        st.caption("Rules are enforced in the database: a masking policy hides cost and a row access policy hides other sites' rows "
                   "on the semantic view, and APP.RESULTS_FOR, APP.BREAKDOWN_FOR, APP.CONTRIBUTION_FOR, APP.RECEIPTS_FOR and "
                   "APP.ASK_METRIC apply the same rules. Roles are picked in this demo; each one is also a real Snowflake role.")
        checked = table("V_PERSONA_CHECK", "ORDER BY METRIC_ID, PERSONA", limit=200)
        if checked.empty:
            st.info("The per-role check has not been run yet (scripts/verify.py personas).")
        else:
            when = pd.Timestamp(checked.CHECKED_AT.iloc[0]).strftime("%d %b %Y %H:%M UTC")
            st.markdown(f"**Same number for every team, checked by logging in as each role** · {when} · "
                        f"{'passed' if bool(checked.PASSED.iloc[0]) else 'FAILED'}")
            st.caption("Each Snowflake persona role read APP.SV_RESULT itself. On the answers every role may see (network, part, "
                       "region and Americas-site answers), the fingerprint of every published value must equal the planner's. "
                       "Other-site answers are the rows outside Americas; logistics must see none.")
            show(st, checked[["PERSONA", "SNOWFLAKE_ROLE", "METRIC_ID", "ROWS_VISIBLE", "VALUES_VISIBLE", "OTHER_SITE_ROWS",
                              "MATCHES_PLANNER"]]
                 .assign(METRIC_ID=checked.METRIC_ID.map(lambda m: METRICS.get(m, {}).get("short", m)))
                 .rename(columns={"PERSONA": "Persona", "SNOWFLAKE_ROLE": "Snowflake role", "METRIC_ID": "Measure",
                                  "ROWS_VISIBLE": "Shared answers read", "VALUES_VISIBLE": "Values not masked",
                                  "OTHER_SITE_ROWS": "Other-site answers", "MATCHES_PLANNER": "Same as planner"}))
    with tabs[3]:
        audit = q("SELECT * FROM TABLE(CONCORDIA.APP.AUDIT_FOR(?)) ORDER BY CREATED_AT DESC LIMIT 300", [persona])
        show(st, audit, height=360)
    with tabs[4]:
        evidence = q("SELECT EVIDENCE_ID, CREATED_AT, PERSONA, QUESTION, METRIC_ID, STATUS, AS_OF, EVIDENCE_HASH FROM "
                     "TABLE(CONCORDIA.APP.EVIDENCE_FOR(?)) ORDER BY CREATED_AT DESC LIMIT 300", [persona])
        show(st, evidence, height=360)
    with tabs[5]:
        st.caption("Field by field: which source field feeds which business field, the rule applied, and what happens if it cannot be mapped.")
        show(st, table("V_SOURCE_MAPPING"), height=360)


PAGE_VIEWS = {"Start here": page_start, "Command center": page_command_center, "Ask Concordia": page_ask, "Why it changed": page_bridge,
              "As-of replay": page_asof, "One graph": page_graph, "Governance": page_governance}
PAGE_VIEWS[page]()
