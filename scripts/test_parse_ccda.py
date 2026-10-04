"""Self-check for the Synthea C-CDA parser."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import parse_ccda

PATIENT_A = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
PATIENT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def document_xml(document_id: str, patient_id: str, description: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ClinicalDocument xmlns="urn:hl7-org:v3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <id root="2.16.840.1.113883.19.5" extension="{document_id}"/>
  <code code="34133-9" codeSystem="2.16.840.1.113883.6.1"/>
  <effectiveTime value="20260824222000"/>
  <recordTarget>
    <patientRole>
      <id root="2.16.840.1.113883.19.5" extension="{patient_id}"/>
    </patientRole>
  </recordTarget>
  <component>
    <structuredBody>
      <component>
        <section>
          <code code="48765-2" codeSystem="2.16.840.1.113883.6.1"/>
          <title>Allergies and Adverse Reactions</title>
          <text>
            <table>
              <thead><tr><th>Start</th><th>Stop</th><th>Description</th><th>Code</th></tr></thead>
              <tbody>
                <tr>
                  <td>2005-06-18T13:20:00Z</td>
                  <td></td>
                  <td ID="allergies-desc-1">Allergic disposition (finding)</td>
                  <td ID="allergies-code-1">http://snomed.info/sct 609328004</td>
                </tr>
              </tbody>
            </table>
          </text>
          <entry>
            <act>
              <code nullFlavor="NA"/>
              <entryRelationship>
                <observation>
                  <code code="ASSERTION" codeSystem="2.16.840.1.113883.5.4"/>
                  <text><reference value="#allergies-desc-1"/></text>
                  <value xsi:type="CD" code="419199007" codeSystem="2.16.840.1.113883.6.96"/>
                  <participant>
                    <participantRole>
                      <playingEntity>
                        <code code="609328004" codeSystem="2.16.840.1.113883.6.96">
                          <originalText><reference value="#allergies-desc-1"/></originalText>
                        </code>
                      </playingEntity>
                    </participantRole>
                  </participant>
                </observation>
              </entryRelationship>
            </act>
          </entry>
        </section>
      </component>
      <component>
        <section>
          <code code="10160-0" codeSystem="2.16.840.1.113883.6.1"/>
          <title>Medications</title>
          <text>
            <table>
              <thead><tr><th>Start</th><th>Stop</th><th>Description</th><th>Code</th></tr></thead>
              <tbody>
                <tr>
                  <td>2005-06-18T13:48:14Z</td>
                  <td></td>
                  <td ID="medications-desc-1">{description}</td>
                  <td ID="medications-code-1">http://www.nlm.nih.gov/research/umls/rxnorm 997501</td>
                </tr>
              </tbody>
            </table>
          </text>
          <entry>
            <substanceAdministration>
              <consumable>
                <manufacturedProduct>
                  <manufacturedMaterial>
                    <code code="997501" codeSystem="2.16.840.1.113883.6.88">
                      <originalText><reference value="#medications-desc-1"/></originalText>
                    </code>
                  </manufacturedMaterial>
                </manufacturedProduct>
              </consumable>
            </substanceAdministration>
          </entry>
        </section>
      </component>
    </structuredBody>
  </component>
</ClinicalDocument>
"""


def write_corpus(root: Path, files: dict[str, str], patients: list[str]) -> tuple[Path, Path, Path]:
    ccda = root / "ccda"
    csv_dir = root / "csv"
    ccda.mkdir()
    csv_dir.mkdir()
    for name, body in files.items():
        (ccda / name).write_text(body, encoding="utf-8")
    patient_rows = ["Id", *patients]
    (csv_dir / "patients.csv").write_text("\n".join(patient_rows) + "\n", encoding="utf-8")
    med_lines = ["START,STOP,PATIENT,PAYER,ENCOUNTER,CODE,DESCRIPTION"]
    allergy_lines = ["START,STOP,PATIENT,ENCOUNTER,CODE,SYSTEM,DESCRIPTION"]
    for patient_id in patients:
        med_lines.append(f"2005-06-18T13:48:14Z,,{patient_id},payer,enc-{patient_id[:8]},997501,Fexofenadine")
        allergy_lines.append(f"2005-06-18,,{patient_id},enc-alg-{patient_id[:8]},609328004,SNOMED-CT,Allergic disposition (finding)")
    (csv_dir / "medications.csv").write_text("\n".join(med_lines) + "\n", encoding="utf-8")
    (csv_dir / "allergies.csv").write_text("\n".join(allergy_lines) + "\n", encoding="utf-8")
    return ccda, csv_dir / "patients.csv", csv_dir


class ParseCcdaTests(unittest.TestCase):
    def test_published_counts_match_narrative_total(self) -> None:
        desc = sum(parse_ccda.EXPECTED_DESC_COUNTS.values())
        self.assertEqual(desc * 2, parse_ccda.EXPECTED_NARRATIVE_ROWS)
        self.assertEqual(parse_ccda.EXPECTED_NARRATIVE_ROWS, 96806)
        self.assertEqual(parse_ccda.EXPECTED_DESC_COUNTS["medications"], 3850)
        self.assertEqual(parse_ccda.EXPECTED_DESC_COUNTS["allergies"], 105)
        self.assertIn("document_id", parse_ccda.COLUMNS)
        self.assertIn("rejected_codes", parse_ccda.COLUMNS)
        self.assertIn("quote_safe", parse_ccda.COLUMNS)

    def test_safe_quote_commas_newlines_and_order(self) -> None:
        description = 'Fexofenadine, 60 MG&#10;"tablet"'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                f"Note_D'Amore_{PATIENT_A}.xml": document_xml(PATIENT_A, PATIENT_A, description),
                f"Zed_{PATIENT_B}.xml": document_xml(PATIENT_B, PATIENT_B, "Plain tablet"),
            }
            ccda, patients, csv_dir = write_corpus(root, files, [PATIENT_A, PATIENT_B])
            result = parse_ccda.parse_corpus(ccda, patients, csv_dir, expected_documents=0)
            self.assertEqual(result.exit_code, 0, result.failures)
            self.assertEqual([row["document_id"] for row in result.rows[:4]], [PATIENT_A] * 4)
            self.assertEqual(result.rows[0]["ordinal"], "1")
            self.assertEqual(result.rows[-1]["document_id"], PATIENT_B)
            allergy = next(row for row in result.rows if row["document_id"] == PATIENT_A and row["element_id"] == "allergies-desc-1")
            self.assertEqual(allergy["code"], "609328004")
            self.assertNotEqual(allergy["code"], "419199007")
            self.assertIn("419199007", allergy["rejected_codes"].split("|"))
            self.assertEqual(allergy["structured_code"], "609328004")
            self.assertEqual(allergy["quote_safe"], "Y")
            self.assertEqual(allergy["csv_match"], "Y")
            self.assertEqual(allergy["csv_encounter"], "enc-alg-aaaaaaaa")
            self.assertEqual(allergy["code_system"], "2.16.840.1.113883.6.96")
            medication = next(row for row in result.rows if row["document_id"] == PATIENT_A and row["element_id"] == "medications-desc-1")
            self.assertEqual(medication["text"], 'Fexofenadine, 60 MG\n"tablet"')
            self.assertEqual(medication["code"], "997501")
            self.assertEqual(medication["section_loinc"], "10160-0")
            output = root / "out"
            parse_ccda.write_outputs(result, output)
            with (output / "document_section.csv").open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                loaded = list(reader)
                self.assertEqual(reader.fieldnames, list(parse_ccda.COLUMNS))
            reloaded = next(row for row in loaded if row["element_id"] == "medications-desc-1" and row["document_id"] == PATIENT_A)
            self.assertEqual(reloaded["text"], 'Fexofenadine, 60 MG\n"tablet"')
            self.assertEqual(len(loaded), 8)

    def test_prefixed_namespace(self) -> None:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<hl7:ClinicalDocument xmlns:hl7="urn:hl7-org:v3">
  <hl7:id extension="{PATIENT_A}"/>
  <hl7:code code="34133-9"/>
  <hl7:effectiveTime value="20260824222000"/>
  <hl7:recordTarget>
    <hl7:patientRole><hl7:id extension="{PATIENT_A}"/></hl7:patientRole>
  </hl7:recordTarget>
  <hl7:component>
    <hl7:structuredBody>
      <hl7:component>
        <hl7:section>
          <hl7:code code="10160-0"/>
          <hl7:title>Medications</hl7:title>
          <hl7:text>
            <hl7:table>
              <hl7:thead><hl7:tr><hl7:th>Start</hl7:th><hl7:th>Stop</hl7:th><hl7:th>Description</hl7:th><hl7:th>Code</hl7:th></hl7:tr></hl7:thead>
              <hl7:tbody>
                <hl7:tr>
                  <hl7:td>2005-06-18T13:48:14Z</hl7:td>
                  <hl7:td></hl7:td>
                  <hl7:td ID="medications-desc-1">Plain tablet</hl7:td>
                  <hl7:td ID="medications-code-1">http://www.nlm.nih.gov/research/umls/rxnorm 997501</hl7:td>
                </hl7:tr>
              </hl7:tbody>
            </hl7:table>
          </hl7:text>
        </hl7:section>
      </hl7:component>
    </hl7:structuredBody>
  </hl7:component>
</hl7:ClinicalDocument>
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ccda, patients, csv_dir = write_corpus(root, {f"Prefixed_{PATIENT_A}.xml": xml}, [PATIENT_A])
            (csv_dir / "allergies.csv").unlink()
            result = parse_ccda.parse_corpus(ccda, patients, csv_dir, expected_documents=0)
            self.assertEqual(result.exit_code, 0, result.failures)
            row = next(item for item in result.rows if item["element_id"] == "medications-desc-1")
            self.assertEqual(row["code"], "997501")
            self.assertEqual(row["patient_id"], PATIENT_A)

    def test_filename_mismatch_is_identity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong = f"Note_{PATIENT_B}.xml"
            ccda, patients, csv_dir = write_corpus(
                root,
                {wrong: document_xml(PATIENT_A, PATIENT_A, "Plain tablet")},
                [PATIENT_A],
            )
            result = parse_ccda.parse_corpus(ccda, patients, csv_dir, expected_documents=0)
            self.assertEqual(result.exit_code, 1)
            self.assertTrue(any(item.startswith("identity:") and "filename UUID" in item for item in result.failures))

    def test_patient_document_mismatch_is_identity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ccda, patients, csv_dir = write_corpus(
                root,
                {f"Note_{PATIENT_A}.xml": document_xml(PATIENT_A, PATIENT_B, "Plain tablet")},
                [PATIENT_A, PATIENT_B],
            )
            result = parse_ccda.parse_corpus(ccda, patients, csv_dir, expected_documents=0)
            self.assertIn(result.exit_code, {1, 3})
            self.assertTrue(any("document id" in item and "patient id" in item for item in result.failures))

    def test_missing_patient_is_identity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ccda, patients, csv_dir = write_corpus(
                root,
                {f"Note_{PATIENT_A}.xml": document_xml(PATIENT_A, PATIENT_A, "Plain tablet")},
                [PATIENT_B],
            )
            result = parse_ccda.parse_corpus(ccda, patients, csv_dir, expected_documents=0)
            self.assertNotEqual(result.exit_code, 0)
            self.assertTrue(any(item.startswith("identity:") for item in result.failures))


if __name__ == "__main__":
    unittest.main()
