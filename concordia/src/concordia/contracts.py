"""Frozen identifiers. This module does not calculate metrics."""

METRIC_VERSION = "1.0.0"
SIM_CONTRACT = "CONCORDIA_SIM_V1"
MASTER_SEED = "20261002"

STREAMS = (
    "demand",
    "supply",
    "production",
    "quality",
    "transit",
    "commercial",
    "feedback",
    "defects",
)

ALLOWED_ORIGINS = (
    "SYNTHETIC_ERP",
    "SYNTHETIC_MES",
    "SYNTHETIC_WMS",
    "SYNTHETIC_TMS",
    "SYNTHETIC_CRM",
    "DERIVED_FROM_SYNTHETIC",
)

FORBIDDEN_ORIGINS = (
    "OBSERVED",
    "EVAL_GOLD",
    "INJECTED_DEFECT",
)

PRODUCT_ORIGINS = ALLOWED_ORIGINS

METRICS = (
    {
        "metric_id": "INBOUND_SUPPLIER_OTD",
        "version": METRIC_VERSION,
        "grain": "purchase_order_schedule_line",
    },
    {
        "metric_id": "OUTBOUND_CUSTOMER_OTD",
        "version": METRIC_VERSION,
        "grain": "sales_order_line",
    },
    {
        "metric_id": "UNIT_FILL_RATE",
        "version": METRIC_VERSION,
        "grain": "sales_order_line",
    },
    {
        "metric_id": "DAYS_INVENTORY",
        "version": METRIC_VERSION,
        "grain": "facility_item_as_of",
    },
    {
        "metric_id": "LANDED_COST_PER_ACCEPTED_UNIT",
        "version": METRIC_VERSION,
        "grain": "accepted_receipt",
    },
)

SUPPORTED_INCOTERMS = ("EXW", "FCA", "DAP", "DDP")
