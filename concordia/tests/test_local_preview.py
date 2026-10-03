"""Static guarantees for the Streamlit app: it reads the governed APP layer and never computes a metric."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "streamlit" / "app.py").read_text(encoding="utf-8")


def test_app_reads_only_the_app_layer():
    referenced = set(re.findall(r"CONCORDIA\.([A-Z_]+)\.", APP))
    assert referenced == {"APP"}
    for schema in ("CORE.", "LAND.", "GOV.", "SIM."):
        assert f"CONCORDIA.{schema}" not in APP
        assert not re.search(rf"\bFROM\s+{re.escape(schema)}", APP)


def test_app_does_not_import_the_oracle_or_fixtures():
    lowered = APP.lower()
    for forbidden in ("concordia.metrics", "run_case", "golden_v1", "local_data", "fixture"):
        assert forbidden not in lowered


def test_app_never_labels_data_as_observed():
    assert "observed" not in APP.lower()


def test_app_has_no_arithmetic_on_metric_values():
    for column in ("VALUE_NUM", "NUMERATOR", "DENOMINATOR", "DISPLAY", "PERCENT_DISPLAY"):
        assert not re.search(rf"{column}[\"'\]\)]*\s*[*/+-]\s*[\d(]", APP)
        assert not re.search(rf"[\d)]\s*[*/]\s*\w*\[?[\"']?{column}", APP)


def test_synthetic_disclosure_is_visible():
    assert "Synthetic world CONCORDIA_SIM_V1" in APP
