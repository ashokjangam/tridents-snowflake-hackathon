"""Parse Synthea C-CDA files into RAW.DOCUMENT_SECTION rows.

The citation grain is (document_id, element_id). ``code`` is the code written
in the narrative table. Allergy assertion values such as 419199007 stay in
``rejected_codes`` and are not copied into ``code``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PATIENT360_DIR = SCRIPT_DIR.parent
REPO_ROOT = PATIENT360_DIR.parent

DEFAULT_CCDA_DIR = REPO_ROOT / "data" / "patient-360" / "ccda"
DEFAULT_PATIENTS_CSV = REPO_ROOT / "data" / "patient-360" / "csv" / "patients.csv"
DEFAULT_CSV_DIR = REPO_ROOT / "data" / "patient-360" / "csv"
DEFAULT_OUTPUT_DIR = PATIENT360_DIR / "generated"

FULL_SAMPLE_DOCUMENTS = 108
EXPECTED_NARRATIVE_ROWS = 96806
WORKED_DOCUMENT = "37549f60-b5a3-69cd-dea6-5a71c4bc23cf"

COLUMNS = (
    "document_id",
    "patient_id",
    "effective_time",
    "section_loinc",
    "section_title",
    "element_id",
    "text",
    "code",
    "code_system",
    "source_file",
    "element_role",
    "row_start",
    "row_stop",
    "row_value",
    "narrative_code",
    "narrative_system_uri",
    "code_system_name",
    "structured_code",
    "structured_code_system",
    "rejected_codes",
    "quote_safe",
    "csv_table",
    "csv_match",
    "csv_encounter",
    "csv_start",
    "ordinal",
)

EXPECTED_DESC_COUNTS = {
    "medications": 3850,
    "allergies": 105,
    "conditions": 3517,
    "encounters": 5571,
    "procedures": 15884,
    "immunizations": 1549,
    "careplans": 349,
    "observations": 9784,
    "reports": 5363,
    "functional-status": 2431,
}

EXPECTED_SECTION_TITLES = {
    ("47519-4", "Surgeries"): 107,
    ("47519-4", "Procedures"): 1,
    ("48765-2", "Allergies and Adverse Reactions"): 21,
    ("48765-2", "Allergies"): 87,
}

EXPECTED_SECTION_FILES = {
    "10160-0": 108,
    "30954-2": 108,
    "11450-4": 108,
    "46240-8": 108,
    "8716-3": 108,
    "11369-6": 108,
    "29762-2": 108,
    "47519-4": 108,
    "18776-5": 101,
    "47420-5": 94,
    "48765-2": 108,
}

CSV_SPECS = {
    "medications": {
        "file": "medications.csv",
        "patient": "PATIENT",
        "code": "CODE",
        "start": "START",
        "encounter": "ENCOUNTER",
    },
    "allergies": {
        "file": "allergies.csv",
        "patient": "PATIENT",
        "code": "CODE",
        "start": "START",
        "encounter": "ENCOUNTER",
    },
    "conditions": {
        "file": "conditions.csv",
        "patient": "PATIENT",
        "code": "CODE",
        "start": "START",
        "encounter": "ENCOUNTER",
    },
    "encounters": {
        "file": "encounters.csv",
        "patient": "PATIENT",
        "code": "CODE",
        "start": "START",
        "encounter": "Id",
    },
    "procedures": {
        "file": "procedures.csv",
        "patient": "PATIENT",
        "code": "CODE",
        "start": "START",
        "encounter": "ENCOUNTER",
    },
    "immunizations": {
        "file": "immunizations.csv",
        "patient": "PATIENT",
        "code": "CODE",
        "start": "DATE",
        "encounter": "ENCOUNTER",
    },
    "careplans": {
        "file": "careplans.csv",
        "patient": "PATIENT",
        "code": "CODE",
        "start": "START",
        "encounter": "ENCOUNTER",
    },
}

SYSTEMS = {
    "http://snomed.info/sct": ("2.16.840.1.113883.6.96", "SNOMED-CT"),
    "http://www.nlm.nih.gov/research/umls/rxnorm": ("2.16.840.1.113883.6.88", "RxNorm"),
    "http://loinc.org": ("2.16.840.1.113883.6.1", "LOINC"),
    "http://hl7.org/fhir/sid/cvx": ("2.16.840.1.113883.12.292", "CVX"),
}

FILENAME_UUID = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.xml$",
    re.IGNORECASE,
)
ELEMENT_ID_RE = re.compile(r"^(?P<prefix>.+)-(?P<role>desc|code)-(?P<num>\d+)$")
CODE_TEXT_RE = re.compile(r"^(\S+)\s+(\S+)$")
CLINICAL_CODE_TAGS = {"code", "value", "translation"}
SKIP_CODES = {"ASSERTION"}

csv.field_size_limit(10_000_000)


@dataclass(frozen=True)
class CsvFact:
    patient_id: str
    code: str
    start: str
    encounter: str


@dataclass(frozen=True)
class StructuredFacts:
    owners: tuple[tuple[str, str], ...] = ()
    distractors: tuple[tuple[str, str], ...] = ()

    def union(self, other: StructuredFacts) -> StructuredFacts:
        return StructuredFacts(
            owners=_unique(self.owners + other.owners),
            distractors=_unique(self.distractors + other.distractors),
        )


@dataclass
class ParseResult:
    rows: list[dict[str, str]]
    failures: list[str]
    summary: dict[str, object]

    @property
    def exit_code(self) -> int:
        return classify_exit(self.failures)


def _unique(items: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    return tuple(dict.fromkeys(items))


def classify_exit(failures: list[str]) -> int:
    identity = any(item.startswith("identity:") for item in failures)
    count = any(item.startswith("count:") for item in failures)
    if identity and count:
        return 3
    if identity:
        return 1
    if count:
        return 2
    return 0


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def cell_text(element: ET.Element) -> str:
    chunks: list[str] = []
    if element.text:
        chunks.append(element.text)
    for child in list(element):
        chunks.append(cell_text(child))
        if child.tail:
            chunks.append(child.tail)
    raw = "".join(chunks).replace("\r\n", "\n").replace("\r", "\n")
    return raw.strip()


def xml_id(element: ET.Element) -> str:
    if "ID" in element.attrib:
        return element.attrib["ID"].strip()
    if "id" in element.attrib:
        return element.attrib["id"].strip()
    for key, value in element.attrib.items():
        if key.endswith("}ID") or key.endswith("}id"):
            return value.strip()
    return ""


def direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == name]


def parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    parents: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in list(parent):
            parents[child] = parent
    return parents


def ancestor(node: ET.Element, name: str, parents: dict[ET.Element, ET.Element]) -> ET.Element | None:
    current = parents.get(node)
    while current is not None:
        if local_name(current.tag) == name:
            return current
        current = parents.get(current)
    return None


def filename_uuid(name: str) -> str:
    match = FILENAME_UUID.search(name)
    if match is None:
        return ""
    return match.group(1)


def pair_element_id(element_id: str) -> str:
    match = ELEMENT_ID_RE.fullmatch(element_id)
    if match is None:
        return ""
    other = "code" if match.group("role") == "desc" else "desc"
    return f"{match.group('prefix')}-{other}-{match.group('num')}"


def element_prefix(element_id: str) -> str:
    match = ELEMENT_ID_RE.fullmatch(element_id)
    if match is None:
        return ""
    return match.group("prefix")


def element_role(element_id: str) -> str:
    match = ELEMENT_ID_RE.fullmatch(element_id)
    if match is None:
        return "other"
    if match.group("role") == "desc":
        return "description"
    return "code"


def parse_code_text(text: str) -> tuple[str, str]:
    match = CODE_TEXT_RE.fullmatch(text.strip())
    if match is None:
        return "", ""
    return match.group(2), match.group(1)


def find_document(root: ET.Element) -> ET.Element | None:
    if local_name(root.tag) == "ClinicalDocument":
        return root
    for node in root.iter():
        if local_name(node.tag) == "ClinicalDocument":
            return node
    return None


def load_patient_ids(path: Path) -> tuple[set[str], list[str]]:
    failures: list[str] = []
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "Id" not in reader.fieldnames:
                return set(), [f"identity: {path.name} has no Id column"]
            patient_ids = {(row.get("Id") or "").strip() for row in reader}
    except OSError as exc:
        return set(), [f"identity: cannot read {path}: {exc}"]
    patient_ids.discard("")
    if not patient_ids:
        failures.append(f"identity: {path.name} has no patient ids")
    return patient_ids, failures


def load_csv_pools(csv_dir: Path, desc_counts: dict[str, int]) -> tuple[dict[str, dict[tuple[str, str, str], list[CsvFact]]], dict[str, int], list[str]]:
    pools: dict[str, dict[tuple[str, str, str], list[CsvFact]]] = {}
    sizes: dict[str, int] = {}
    failures: list[str] = []
    for table, spec in CSV_SPECS.items():
        path = csv_dir / str(spec["file"])
        if not path.exists():
            if desc_counts.get(table, 0) > 0:
                failures.append(f"count: missing reconciliation file {path.name} for {table}")
            continue
        pool: dict[tuple[str, str, str], list[CsvFact]] = defaultdict(list)
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                fieldnames = reader.fieldnames or []
                required = [str(spec["patient"]), str(spec["code"]), str(spec["start"]), str(spec["encounter"])]
                missing = [column for column in required if column not in fieldnames]
                if missing:
                    failures.append(f"count: {path.name} missing columns {', '.join(missing)}")
                    continue
                count = 0
                for row in reader:
                    fact = CsvFact(
                        patient_id=(row.get(str(spec["patient"])) or "").strip(),
                        code=(row.get(str(spec["code"])) or "").strip(),
                        start=(row.get(str(spec["start"])) or "").strip(),
                        encounter=(row.get(str(spec["encounter"])) or "").strip(),
                    )
                    pool[(fact.patient_id, fact.code, fact.start)].append(fact)
                    count += 1
        except OSError as exc:
            failures.append(f"count: cannot read {path.name}: {exc}")
            continue
        for facts in pool.values():
            facts.sort(key=lambda fact: (fact.encounter, fact.start, fact.code, fact.patient_id))
        pools[table] = pool
        sizes[table] = count
    return pools, sizes, failures


def take_fact(pool: dict[tuple[str, str, str], list[CsvFact]], patient_id: str, code: str, row_start: str) -> CsvFact | None:
    row_start = row_start.strip()
    exact = pool.get((patient_id, code, row_start))
    if exact:
        return exact.pop(0)
    if len(row_start) >= 10 and row_start[4] == "-" and row_start[7] == "-":
        day = row_start[:10]
        if day != row_start:
            dated = pool.get((patient_id, code, day))
            if dated:
                return dated.pop(0)
    return None


def code_owner(ref: ET.Element, parents: dict[ET.Element, ET.Element]) -> ET.Element | None:
    parent = parents.get(ref)
    if parent is None or local_name(parent.tag) != "originalText":
        return None
    owner = parents.get(parent)
    if owner is None or local_name(owner.tag) not in CLINICAL_CODE_TAGS:
        return None
    return owner


def structured_by_element(section: ET.Element, parents: dict[ET.Element, ET.Element]) -> dict[str, StructuredFacts]:
    text_nodes = {child for child in direct_children(section, "text")}
    collected: dict[str, StructuredFacts] = {}
    for entry in section.iter():
        if local_name(entry.tag) != "entry":
            continue
        if ancestor(entry, "entry", parents) is not None:
            continue
        if _under(entry, text_nodes, parents):
            continue
        owners_by_id: dict[str, list[tuple[str, str]]] = defaultdict(list)
        referenced: set[str] = set()
        owner_ids: set[int] = set()
        for node in entry.iter():
            if local_name(node.tag) != "reference":
                continue
            target = _reference_target(node)
            if not target:
                continue
            referenced.add(target)
            owner = code_owner(node, parents)
            if owner is None:
                continue
            code = (owner.attrib.get("code") or "").strip()
            system = (owner.attrib.get("codeSystem") or "").strip()
            if code and "nullFlavor" not in owner.attrib:
                owners_by_id[target].append((code, system))
                owner_ids.add(id(owner))
        distractors: list[tuple[str, str]] = []
        for node in entry.iter():
            if local_name(node.tag) not in CLINICAL_CODE_TAGS or id(node) in owner_ids:
                continue
            code = (node.attrib.get("code") or "").strip()
            if not code or "nullFlavor" in node.attrib or code in SKIP_CODES:
                continue
            distractors.append((code, (node.attrib.get("codeSystem") or "").strip()))
        distractor_tuple = _unique(tuple(distractors))
        for element_id in referenced:
            facts = StructuredFacts(
                owners=_unique(tuple(owners_by_id.get(element_id, []))),
                distractors=distractor_tuple,
            )
            existing = collected.get(element_id)
            collected[element_id] = facts if existing is None else existing.union(facts)
    expanded = dict(collected)
    for element_id, facts in collected.items():
        partner = pair_element_id(element_id)
        if not partner:
            continue
        other = expanded.get(partner)
        expanded[partner] = facts if other is None else other.union(facts)
    return expanded


def _reference_target(node: ET.Element) -> str:
    value = (node.attrib.get("value") or "").strip()
    if value.startswith("#") and len(value) > 1:
        return value[1:]
    return ""


def _under(node: ET.Element, ancestors: set[ET.Element], parents: dict[ET.Element, ET.Element]) -> bool:
    current: ET.Element | None = node
    while current is not None:
        if current in ancestors:
            return True
        current = parents.get(current)
    return False


def table_headers(table: ET.Element, parents: dict[ET.Element, ET.Element], cache: dict[int, list[str]]) -> list[str]:
    key = id(table)
    cached = cache.get(key)
    if cached is not None:
        return cached
    labels: list[str] = []
    for node in table.iter():
        if local_name(node.tag) != "th":
            continue
        if ancestor(node, "thead", parents) is None:
            continue
        labels.append(cell_text(node).casefold())
    cache[key] = labels
    return labels


def row_fields(element: ET.Element, parents: dict[ET.Element, ET.Element], cache: dict[int, list[str]]) -> tuple[str, str, str]:
    host = element if local_name(element.tag) == "td" else ancestor(element, "td", parents)
    if host is None:
        return "", "", ""
    row = ancestor(host, "tr", parents)
    table = ancestor(host, "table", parents)
    if row is None or table is None:
        return "", "", ""
    headers = table_headers(table, parents, cache)
    cells = [child for child in list(row) if local_name(child.tag) == "td"]
    try:
        index = cells.index(host)
    except ValueError:
        return "", "", ""
    values: dict[str, str] = {}
    for header, cell in zip(headers, cells):
        if header:
            values[header] = cell_text(cell)
    return values.get("start", ""), values.get("stop", ""), values.get("value", "")


def blank_row() -> dict[str, str]:
    return {column: "" for column in COLUMNS}


def parse_file(path: Path) -> tuple[dict[str, object], list[tuple[int, dict[str, str]]], list[str]]:
    failures: list[str] = []
    meta: dict[str, object] = {
        "source_file": path.name,
        "document_id": "",
        "patient_id": "",
        "effective_time": "",
        "document_code": "",
        "section_loincs": [],
        "section_titles": {},
    }
    try:
        document = find_document(ET.parse(path).getroot())
    except ET.ParseError as exc:
        failures.append(f"identity: {path.name} is not well-formed XML: {exc}")
        return meta, [], failures
    except OSError as exc:
        failures.append(f"identity: cannot read {path.name}: {exc}")
        return meta, [], failures
    if document is None:
        failures.append(f"identity: {path.name} has no ClinicalDocument")
        return meta, [], failures

    extensions = [
        (child.attrib.get("extension") or "").strip()
        for child in direct_children(document, "id")
        if (child.attrib.get("extension") or "").strip()
    ]
    if len(extensions) != 1:
        failures.append(f"identity: {path.name} has {len(extensions)} document id extensions")
        document_id = extensions[0] if extensions else ""
    else:
        document_id = extensions[0]
    meta["document_id"] = document_id

    record_targets = direct_children(document, "recordTarget")
    patient_ids: list[str] = []
    if len(record_targets) == 1:
        roles = direct_children(record_targets[0], "patientRole")
        if len(roles) == 1:
            patient_ids = [
                (child.attrib.get("extension") or "").strip()
                for child in direct_children(roles[0], "id")
                if (child.attrib.get("extension") or "").strip()
            ]
    unique_patients = list(dict.fromkeys(patient_ids))
    if len(unique_patients) != 1:
        failures.append(f"identity: {path.name} has {len(unique_patients)} recordTarget patient ids")
        patient_id = unique_patients[0] if unique_patients else ""
    else:
        patient_id = unique_patients[0]
    meta["patient_id"] = patient_id

    times = direct_children(document, "effectiveTime")
    effective = (times[0].attrib.get("value") or "").strip() if len(times) == 1 else ""
    if not effective:
        failures.append(f"identity: {path.name} has no document effectiveTime")
    meta["effective_time"] = effective

    doc_codes = [
        (child.attrib.get("code") or "").strip()
        for child in direct_children(document, "code")
        if (child.attrib.get("code") or "").strip()
    ]
    meta["document_code"] = doc_codes[0] if doc_codes else ""

    file_uuid = filename_uuid(path.name)
    if not file_uuid:
        failures.append(f"identity: {path.name} has no trailing patient UUID")
    elif file_uuid != document_id:
        failures.append(f"identity: {path.name} filename UUID {file_uuid} != document id {document_id}")
    if document_id and patient_id and document_id != patient_id:
        failures.append(f"identity: {path.name} document id {document_id} != patient id {patient_id}")

    body = None
    for component in direct_children(document, "component"):
        bodies = direct_children(component, "structuredBody")
        if bodies:
            body = bodies[0]
            break
    if body is None:
        failures.append(f"identity: {path.name} has no structuredBody")
        return meta, [], failures

    parents = parent_map(body)
    header_cache: dict[int, list[str]] = {}
    rows: list[tuple[int, dict[str, str]]] = []
    seen_ids: set[str] = set()
    seen_loincs: set[str] = set()
    section_loincs: list[str] = []
    section_titles: dict[str, str] = {}
    seq = 0
    for component in body.iter():
        if local_name(component.tag) != "component":
            continue
        for section in direct_children(component, "section"):
            loinc = ""
            for child in direct_children(section, "code"):
                loinc = (child.attrib.get("code") or "").strip()
                if loinc:
                    break
            title_nodes = direct_children(section, "title")
            title = cell_text(title_nodes[0]) if title_nodes else ""
            if not loinc:
                failures.append(f"identity: {path.name} has a section without a LOINC code")
                continue
            if loinc in seen_loincs:
                failures.append(f"identity: {path.name} repeats section {loinc}")
            seen_loincs.add(loinc)
            section_loincs.append(loinc)
            section_titles[loinc] = title
            text_nodes = direct_children(section, "text")
            if not text_nodes:
                continue
            facts = structured_by_element(section, parents)
            by_text: dict[str, str] = {}
            pending: list[tuple[str, str, str, str, str]] = []
            for node in text_nodes[0].iter():
                element_id = xml_id(node)
                if not element_id:
                    continue
                text = cell_text(node)
                row_start, row_stop, row_value = row_fields(node, parents, header_cache)
                by_text[element_id] = text
                pending.append((element_id, text, row_start, row_stop, row_value))
            for element_id, text, row_start, row_stop, row_value in pending:
                if element_id in seen_ids:
                    failures.append(f"identity: {path.name} repeats element id {element_id}")
                    continue
                seen_ids.add(element_id)
                role = element_role(element_id)
                prefix = element_prefix(element_id)
                if role == "code":
                    narrative_code, system_uri = parse_code_text(text)
                else:
                    partner = pair_element_id(element_id)
                    narrative_code, system_uri = parse_code_text(by_text.get(partner, ""))
                oid, system_name = SYSTEMS.get(system_uri, ("", ""))
                structured = facts.get(element_id, StructuredFacts())
                matched_owners = [item for item in structured.owners if item[0] == narrative_code]
                chosen = matched_owners[0] if matched_owners else (structured.owners[0] if structured.owners else ("", ""))
                if not oid and chosen[0] == narrative_code:
                    oid = chosen[1]
                rejected = sorted({code for code, _system in structured.distractors if code and code != narrative_code})
                quote_safe = "Y" if narrative_code and narrative_code not in rejected else "N"
                seq += 1
                row = blank_row()
                row.update(
                    {
                        "document_id": document_id,
                        "patient_id": patient_id,
                        "effective_time": effective,
                        "section_loinc": loinc,
                        "section_title": title,
                        "element_id": element_id,
                        "text": text,
                        "code": narrative_code,
                        "code_system": oid,
                        "source_file": path.name,
                        "element_role": role,
                        "row_start": row_start,
                        "row_stop": row_stop,
                        "row_value": row_value,
                        "narrative_code": narrative_code,
                        "narrative_system_uri": system_uri,
                        "code_system_name": system_name,
                        "structured_code": chosen[0],
                        "structured_code_system": chosen[1],
                        "rejected_codes": "|".join(rejected),
                        "quote_safe": quote_safe,
                        "csv_table": prefix if prefix in CSV_SPECS else "",
                    }
                )
                rows.append((seq, row))
    meta["section_loincs"] = section_loincs
    meta["section_titles"] = section_titles
    return meta, rows, failures


def reconcile(rows: list[dict[str, str]], pools: dict[str, dict[tuple[str, str, str], list[CsvFact]]]) -> None:
    for row in rows:
        table = row["csv_table"]
        if row["element_role"] != "description" or not table:
            continue
        pool = pools.get(table)
        if pool is None:
            row["csv_match"] = "N"
            continue
        fact = take_fact(pool, row["patient_id"], row["narrative_code"], row["row_start"])
        if fact is None:
            row["csv_match"] = "N"
            continue
        row["csv_match"] = "Y"
        row["csv_encounter"] = fact.encounter
        row["csv_start"] = fact.start
    descriptions = {
        (row["document_id"], row["element_id"]): row
        for row in rows
        if row["element_role"] == "description"
    }
    for row in rows:
        if row["element_role"] != "code" or not row["csv_table"]:
            continue
        partner = descriptions.get((row["document_id"], pair_element_id(row["element_id"])))
        if partner is None:
            row["csv_match"] = "N"
            continue
        row["csv_match"] = partner["csv_match"]
        row["csv_encounter"] = partner["csv_encounter"]
        row["csv_start"] = partner["csv_start"]


def _add_check(checks: list[dict[str, object]], failures: list[str], name: str, actual: int, expected: int, kind: str) -> None:
    ok = actual == expected
    checks.append({"name": name, "actual": actual, "expected": expected, "ok": ok})
    if not ok:
        failures.append(f"{kind}: {name} actual {actual} expected {expected}")


def evaluate(
    rows: list[dict[str, str]],
    metas: list[dict[str, object]],
    patient_ids: set[str],
    pools: dict[str, dict[tuple[str, str, str], list[CsvFact]]],
    csv_sizes: dict[str, int],
    failures: list[str],
    expected_documents: int,
) -> dict[str, object]:
    doc_ids = [str(meta["document_id"]) for meta in metas if meta["document_id"]]
    doc_set = set(doc_ids)
    if len(doc_ids) != len(doc_set):
        failures.append(f"identity: duplicate document ids {len(doc_ids) - len(doc_set)}")
    missing_files = sorted(patient_ids - doc_set)
    unknown_docs = sorted(doc_set - patient_ids)
    if missing_files or unknown_docs:
        failures.append(
            "identity: document ids and patients.csv differ "
            f"(patients without a file {len(missing_files)}, files without a patient {len(unknown_docs)}; "
            f"sample { (missing_files + unknown_docs)[:6] })"
        )
    if expected_documents > 0:
        _add_check(checks := [], failures, "documents", len(doc_set), expected_documents, "identity")
    else:
        checks = []

    desc_counts: dict[str, int] = defaultdict(int)
    code_counts: dict[str, int] = defaultdict(int)
    section_files: dict[str, set[str]] = defaultdict(set)
    section_titles: dict[tuple[str, str], int] = defaultdict(int)
    keys: set[tuple[str, str]] = set()
    duplicate_keys = 0
    missing_codes = 0
    unsafe_quotes = 0
    structured_disagreements = 0
    for meta in metas:
        for loinc in meta["section_loincs"]:
            section_files[str(loinc)].add(str(meta["source_file"]))
        titles = meta["section_titles"]
        if isinstance(titles, dict):
            for loinc, title in titles.items():
                section_titles[(str(loinc), str(title))] += 1
    for row in rows:
        key = (row["document_id"], row["element_id"])
        if key in keys:
            duplicate_keys += 1
        keys.add(key)
        prefix = element_prefix(row["element_id"]) or "other"
        if row["element_role"] == "description":
            desc_counts[prefix] += 1
        elif row["element_role"] == "code":
            code_counts[prefix] += 1
        else:
            desc_counts[prefix] += 1
        if row["element_role"] in {"description", "code"} and not row["narrative_code"]:
            missing_codes += 1
        if row["csv_table"] and row["quote_safe"] != "Y":
            unsafe_quotes += 1
        if row["csv_table"] in {"medications", "allergies"} and row["structured_code"] and row["structured_code"] != row["narrative_code"]:
            structured_disagreements += 1
    if duplicate_keys:
        failures.append(f"identity: duplicate citation keys {duplicate_keys}")
    if missing_codes:
        failures.append(f"count: narrative cells missing a code {missing_codes}")
    if unsafe_quotes:
        failures.append(f"count: reconciled rows that are not quote_safe {unsafe_quotes}")
    if structured_disagreements:
        failures.append(f"count: medication or allergy structured codes disagree with the narrative {structured_disagreements}")
    for prefix in sorted(set(desc_counts) | set(code_counts)):
        if prefix == "other":
            continue
        if desc_counts[prefix] != code_counts[prefix]:
            failures.append(
                f"count: {prefix} description cells {desc_counts[prefix]} != code cells {code_counts[prefix]}"
            )

    reconciliation: dict[str, dict[str, int]] = {}
    for table in CSV_SPECS:
        narrative = desc_counts.get(table, 0)
        csv_rows = csv_sizes.get(table, 0)
        matched = sum(1 for row in rows if row["csv_table"] == table and row["element_role"] == "description" and row["csv_match"] == "Y")
        unmatched_rows = [
            row for row in rows
            if row["csv_table"] == table and row["element_role"] == "description" and row["csv_match"] != "Y"
        ]
        left = sum(len(facts) for facts in pools.get(table, {}).values())
        reconciliation[table] = {
            "narrative_desc": narrative,
            "csv_rows": csv_rows,
            "matched": matched,
            "unmatched": len(unmatched_rows),
            "csv_left": left,
        }
        if table in pools or narrative:
            if matched != narrative or left != 0 or (table in csv_sizes and csv_rows != narrative):
                sample = [
                    f"{row['document_id']}:{row['element_id']}:{row['narrative_code']}:{row['row_start']}"
                    for row in unmatched_rows[:5]
                ]
                failures.append(
                    f"count: {table} reconciliation narrative {narrative} csv {csv_rows} "
                    f"matched {matched} csv_left {left} sample {sample}"
                )

    worked = _worked_example(rows)
    if expected_documents == FULL_SAMPLE_DOCUMENTS:
        _add_check(checks, failures, "narrative rows", len(rows), EXPECTED_NARRATIVE_ROWS, "count")
        for prefix, expected in EXPECTED_DESC_COUNTS.items():
            _add_check(checks, failures, f"{prefix} description cells", desc_counts.get(prefix, 0), expected, "count")
        for loinc, expected in EXPECTED_SECTION_FILES.items():
            _add_check(checks, failures, f"section {loinc} files", len(section_files.get(loinc, ())), expected, "count")
        for (loinc, title), expected in EXPECTED_SECTION_TITLES.items():
            _add_check(checks, failures, f"section {loinc} title {title}", section_titles.get((loinc, title), 0), expected, "count")
        extra_loinc = sorted(set(section_files) - set(EXPECTED_SECTION_FILES))
        if extra_loinc:
            failures.append(f"count: unexpected section LOINC {extra_loinc}")
        extra_prefix = sorted((set(desc_counts) | set(code_counts)) - set(EXPECTED_DESC_COUNTS) - {"other"})
        if extra_prefix:
            failures.append(f"count: unexpected element prefixes {extra_prefix}")
        med_files = {row["source_file"] for row in rows if row["element_id"] == "medications-desc-1"}
        _add_check(checks, failures, "files with medications-desc-1", len(med_files), 105, "count")
        doc_codes = [str(meta["document_code"]) for meta in metas]
        _add_check(checks, failures, "document code 34133-9", sum(1 for code in doc_codes if code == "34133-9"), FULL_SAMPLE_DOCUMENTS, "count")
        if any(code != "34133-9" for code in doc_codes):
            failures.append("count: a document code is not LOINC 34133-9")
        if not worked["present"]:
            failures.append(f"count: worked document {WORKED_DOCUMENT} is missing")
        elif not worked["ok"]:
            failures.extend(f"count: {item}" for item in worked["failures"])

    return {
        "documents": len(doc_set),
        "patients_csv": len(patient_ids),
        "rows": len(rows),
        "files": len(metas),
        "desc_counts": dict(sorted(desc_counts.items())),
        "code_counts": dict(sorted(code_counts.items())),
        "section_files": {loinc: len(names) for loinc, names in sorted(section_files.items())},
        "section_titles": {f"{loinc}|{title}": count for (loinc, title), count in sorted(section_titles.items())},
        "reconciliation": reconciliation,
        "worked_example": worked,
        "checks": checks,
        "identity_failures": sum(1 for item in failures if item.startswith("identity:")),
        "count_failures": sum(1 for item in failures if item.startswith("count:")),
        "ok": not failures,
        "exit_code": classify_exit(failures),
        "failures": failures,
    }


def _worked_example(rows: list[dict[str, str]]) -> dict[str, object]:
    wanted = {
        "medications-desc-2": None,
        "medications-code-2": None,
        "allergies-desc-1": None,
        "allergies-code-1": None,
    }
    for row in rows:
        if row["document_id"] == WORKED_DOCUMENT and row["element_id"] in wanted:
            wanted[row["element_id"]] = row
    present = any(row is not None for row in wanted.values())
    problems: list[str] = []
    med = wanted["medications-desc-2"]
    med_code = wanted["medications-code-2"]
    allergy = wanted["allergies-desc-1"]
    allergy_code = wanted["allergies-code-1"]
    if not present:
        return {"present": False, "ok": False, "failures": problems}
    if med is None:
        problems.append("worked medication cell medications-desc-2 is missing")
    else:
        if med["text"] != "Fexofenadine hydrochloride 60 MG Oral Tablet":
            problems.append(f"worked medication text is {med['text']!r}")
        if med["code"] != "997501" or med["narrative_code"] != "997501":
            problems.append(f"worked medication code is {med['code']!r}")
        if med["code_system"] != "2.16.840.1.113883.6.88":
            problems.append(f"worked medication code system is {med['code_system']!r}")
        if med["section_loinc"] != "10160-0" or med["section_title"] != "Medications":
            problems.append("worked medication section is not LOINC 10160-0 Medications")
        if med["row_start"] != "2005-06-18T13:48:14Z":
            problems.append(f"worked medication start is {med['row_start']!r}")
        if med["effective_time"] != "20260824222000":
            problems.append(f"worked effective time is {med['effective_time']!r}")
        if med["quote_safe"] != "Y" or med["csv_match"] != "Y":
            problems.append("worked medication is not a safe CSV match")
        if med["csv_encounter"] != "37549f60-b5a3-69cd-bd30-c7a0b0133ccf":
            problems.append(f"worked medication encounter is {med['csv_encounter']!r}")
        if med["patient_id"] != WORKED_DOCUMENT or med["document_id"] != WORKED_DOCUMENT:
            problems.append("worked medication document and patient ids differ")
    if med_code is None or med_code["code"] != "997501":
        problems.append("worked medications-code-2 is not RxNorm 997501")
    if allergy is None:
        problems.append("worked allergy cell allergies-desc-1 is missing")
    else:
        if allergy["text"] != "Allergic disposition (finding)":
            problems.append(f"worked allergy text is {allergy['text']!r}")
        if allergy["code"] != "609328004":
            problems.append(f"worked allergy code is {allergy['code']!r}")
        if allergy["code"] == "419199007":
            problems.append("worked allergy quote used assertion 419199007")
        rejected = set(allergy["rejected_codes"].split("|")) if allergy["rejected_codes"] else set()
        if "419199007" not in rejected:
            problems.append(f"worked allergy rejected codes are {allergy['rejected_codes']!r}")
        if allergy["structured_code"] != "609328004":
            problems.append(f"worked allergy structured code is {allergy['structured_code']!r}")
        if allergy["quote_safe"] != "Y" or allergy["csv_match"] != "Y":
            problems.append("worked allergy is not a safe CSV match")
        if allergy["csv_encounter"] != "37549f60-b5a3-69cd-bd30-c7a0b0133ccf":
            problems.append(f"worked allergy encounter is {allergy['csv_encounter']!r}")
        if allergy["section_loinc"] != "48765-2":
            problems.append(f"worked allergy section is {allergy['section_loinc']!r}")
        if allergy["row_start"] != "2005-06-18T13:20:00Z":
            problems.append(f"worked allergy start is {allergy['row_start']!r}")
    if allergy_code is None or allergy_code["code"] != "609328004":
        problems.append("worked allergies-code-1 is not SNOMED 609328004")
    elif "419199007" in (allergy_code["rejected_codes"].split("|") if allergy_code["rejected_codes"] else []):
        pass
    return {
        "present": True,
        "ok": not problems,
        "failures": problems,
        "medication_code": None if med is None else med["code"],
        "allergy_code": None if allergy is None else allergy["code"],
        "allergy_rejected_codes": None if allergy is None else allergy["rejected_codes"],
        "medication_encounter": None if med is None else med["csv_encounter"],
        "allergy_encounter": None if allergy is None else allergy["csv_encounter"],
    }


def parse_corpus(ccda_dir: Path, patients_csv: Path, csv_dir: Path, expected_documents: int = FULL_SAMPLE_DOCUMENTS) -> ParseResult:
    failures: list[str] = []
    patient_ids, patient_failures = load_patient_ids(patients_csv)
    failures.extend(patient_failures)
    paths = [path for path in ccda_dir.iterdir() if path.is_file() and path.suffix.casefold() == ".xml"] if ccda_dir.exists() else []
    paths.sort(key=lambda path: path.name.casefold())
    if not paths:
        failures.append(f"identity: no C-CDA xml files in {ccda_dir}")
    collected: list[tuple[str, int, dict[str, str]]] = []
    metas: list[dict[str, object]] = []
    for path in paths:
        meta, file_rows, file_failures = parse_file(path)
        metas.append(meta)
        failures.extend(file_failures)
        for seq, row in file_rows:
            collected.append((path.name.casefold(), seq, row))
    collected.sort(key=lambda item: (item[0], item[1]))
    rows: list[dict[str, str]] = []
    for ordinal, (_name, _seq, row) in enumerate(collected, start=1):
        row["ordinal"] = str(ordinal)
        rows.append(row)
    desc_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["element_role"] == "description":
            prefix = element_prefix(row["element_id"])
            if prefix:
                desc_counts[prefix] += 1
    pools, csv_sizes, csv_failures = load_csv_pools(csv_dir, desc_counts)
    failures.extend(csv_failures)
    reconcile(rows, pools)
    summary = evaluate(rows, metas, patient_ids, pools, csv_sizes, failures, expected_documents)
    summary["expected_documents"] = expected_documents
    return ParseResult(rows=rows, failures=failures, summary=summary)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_outputs(result: ParseResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "document_section.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS), lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in result.rows:
            writer.writerow(row)
    recon_path = output_dir / "reconciliation_summary.csv"
    recon = result.summary.get("reconciliation", {})
    with recon_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["table", "narrative_desc", "csv_rows", "matched", "unmatched", "csv_left"],
            lineterminator="\n",
        )
        writer.writeheader()
        if isinstance(recon, dict):
            for table in CSV_SPECS:
                stats = recon.get(table, {})
                if isinstance(stats, dict):
                    writer.writerow({"table": table, **stats})
    result.summary["output_csv"] = str(csv_path)
    result.summary["output_reconciliation_csv"] = str(recon_path)
    result.summary["output_sha256"] = file_sha256(csv_path)
    result.summary["output_bytes"] = csv_path.stat().st_size
    summary_path = output_dir / "parse_summary.json"
    summary_path.write_text(json.dumps(result.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result.summary["output_summary"] = str(summary_path)


def format_summary(summary: dict[str, object]) -> str:
    lines = [
        f"documents: {summary.get('documents')} (patients.csv {summary.get('patients_csv')})",
        f"narrative_rows: {summary.get('rows')}",
        f"identity_failures: {summary.get('identity_failures')}",
        f"count_failures: {summary.get('count_failures')}",
    ]
    desc_counts = summary.get("desc_counts")
    if isinstance(desc_counts, dict):
        rendered = ", ".join(f"{name}={count}" for name, count in desc_counts.items())
        lines.append(f"description_cells: {rendered}")
    section_files = summary.get("section_files")
    if isinstance(section_files, dict):
        rendered = ", ".join(f"{loinc}={count}" for loinc, count in section_files.items())
        lines.append(f"section_files: {rendered}")
    reconciliation = summary.get("reconciliation")
    if isinstance(reconciliation, dict):
        for table, stats in reconciliation.items():
            if isinstance(stats, dict):
                lines.append(
                    f"{table}: narrative {stats.get('narrative_desc')} csv {stats.get('csv_rows')} "
                    f"matched {stats.get('matched')} left {stats.get('csv_left')}"
                )
    worked = summary.get("worked_example")
    if isinstance(worked, dict) and worked.get("present"):
        lines.append(
            "worked_medication: "
            f"{worked.get('medication_code')} encounter {worked.get('medication_encounter')}"
        )
        lines.append(
            "worked_allergy: "
            f"{worked.get('allergy_code')} rejected {worked.get('allergy_rejected_codes')} "
            f"encounter {worked.get('allergy_encounter')}"
        )
    if summary.get("output_sha256"):
        lines.append(f"output_sha256: {summary.get('output_sha256')}")
        lines.append(f"output_bytes: {summary.get('output_bytes')}")
        lines.append(f"output_csv: {summary.get('output_csv')}")
    lines.append("validation: PASS" if summary.get("ok") else "validation: FAIL")
    return "\n".join(lines)


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def run_self_check() -> int:
    suite = unittest.defaultTestLoader.discover(str(SCRIPT_DIR), pattern="test_parse_ccda.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        return 0
    return 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse Synthea C-CDA files into a DOCUMENT_SECTION CSV.")
    parser.add_argument("--ccda-dir", type=Path, default=DEFAULT_CCDA_DIR)
    parser.add_argument("--patients-csv", type=Path, default=DEFAULT_PATIENTS_CSV)
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-documents", type=int, default=FULL_SAMPLE_DOCUMENTS)
    parser.add_argument("--self-check", action="store_true", help="Run unit tests and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    if args.self_check:
        return run_self_check()
    for path, label in (
        (args.ccda_dir, "C-CDA directory"),
        (args.patients_csv, "patients CSV"),
        (args.csv_dir, "CSV directory"),
    ):
        if not path.exists():
            print(f"identity: missing {label}: {path}", file=sys.stderr)
            return 1
    result = parse_corpus(args.ccda_dir, args.patients_csv, args.csv_dir, args.expected_documents)
    write_outputs(result, args.output_dir)
    print(format_summary(result.summary))
    if result.failures:
        preview = result.failures[:80]
        print("\n".join(preview), file=sys.stderr)
        if len(result.failures) > len(preview):
            print(f"... {len(result.failures) - len(preview)} more failures", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
