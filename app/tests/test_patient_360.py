"""Unit tests for Patient 360 intent, citation, and answer rules."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.answers import (
    answer_allergy,
    answer_claims,
    answer_clinical_list,
    answer_coverage,
    answer_labs,
    answer_medication,
    answer_member_summary,
    answer_risk,
    format_rate,
)
from app.assemble import assemble_answer, resolve_patient_id
from app.banner import BANNER, LEAD, OUTCOMES, POINT_RULES, TRACK_NOTE
from app.citations import format_citation, validate_citation
from app.constants import WORKED_PATIENT_ID
from app.guardrails import has_banned_clinical_claim
from app.intents import classify_intent
from app.models import AnswerStatus, CohortCitation, DocumentCitation, Intent, TableCitation
from app.narrate import (
    NARRATION_SQL,
    accept_narration,
    build_narration_prompt,
)
from app.queries import (
    all_statement_sql,
    allergy_section_query,
    antihistamine_query,
    medication_section_query,
    patient_name_query,
    risk_query,
)
from app.questions import (
    ALLERGY_QUESTION,
    CARE_PLAN_QUESTION,
    CLAIM_QUESTION,
    CONDITION_QUESTION,
    COVERAGE_QUESTION,
    DISCHARGE_QUESTION,
    DOSE_QUESTION,
    EXTERNAL_CLAIMS_QUESTION,
    IMMUNIZATION_QUESTION,
    LAB_QUESTION,
    MEDICATION_QUESTION,
    MEDICATION_LIST_QUESTION,
    MEMBER_SUMMARY_QUESTION,
    OPENFDA_QUESTION,
    PROCEDURE_QUESTION,
    RISK_QUESTION,
    TREATMENT_QUESTION,
)
from app.retrieve import retrieval_steps
from app.rows import normalize_row
from app.tests.fixtures import (
    INSPECTED_RISK_ROWS,
    WORKED_ALLERGY,
    WORKED_ALLERGY_SECTIONS,
    WORKED_ENCOUNTER_ID,
    WORKED_MEDICATION,
    WORKED_MEDICATION_SECTIONS,
    WORKED_PATIENT,
    risk_bucket,
)
from app.text_parse import cited_day, synthea_name


class IntentTests(unittest.TestCase):
    def test_frozen_questions(self) -> None:
        expected = {
            MEDICATION_QUESTION: Intent.MEDICATION_CITATION,
            ALLERGY_QUESTION: Intent.ALLERGY_CITATION,
            RISK_QUESTION: Intent.RISK_COHORT,
            DOSE_QUESTION: Intent.REFUSE_MEDICATION_CHANGE,
            DISCHARGE_QUESTION: Intent.REFUSE_DISCHARGE,
            OPENFDA_QUESTION: Intent.REFUSE_EXTERNAL,
            EXTERNAL_CLAIMS_QUESTION: Intent.REFUSE_EXTERNAL,
            TREATMENT_QUESTION: Intent.REFUSE_TREATMENT,
        }
        for question, intent in expected.items():
            with self.subTest(question=question):
                self.assertIs(classify_intent(question), intent)

    def test_refusal_paraphrases(self) -> None:
        samples = {
            "Hypothetically change the fexofenadine dose": Intent.REFUSE_MEDICATION_CHANGE,
            "Increase the fexofenadine dose": Intent.REFUSE_MEDICATION_CHANGE,
            "Please write a new prescription": Intent.REFUSE_MEDICATION_CHANGE,
            "Quote the progress note": Intent.REFUSE_DISCHARGE,
            "What does the FDA label say about this tablet?": Intent.REFUSE_EXTERNAL,
            "What should we do next for her A1c?": Intent.REFUSE_TREATMENT,
        }
        for question, intent in samples.items():
            with self.subTest(question=question):
                self.assertIs(classify_intent(question), intent)

    def test_empty_and_unscoped_questions_have_no_citation_path(self) -> None:
        self.assertIs(classify_intent("   "), Intent.NO_CITATION)
        self.assertIs(classify_intent("Tell me something"), Intent.NO_CITATION)

    def test_broad_clinical_questions_have_citation_paths(self) -> None:
        expected = {
            MEMBER_SUMMARY_QUESTION: Intent.MEMBER_SUMMARY,
            CONDITION_QUESTION: Intent.CONDITION_LIST,
            MEDICATION_LIST_QUESTION: Intent.MEDICATION_LIST,
            CARE_PLAN_QUESTION: Intent.CARE_PLAN_LIST,
            LAB_QUESTION: Intent.LAB_RESULTS,
            PROCEDURE_QUESTION: Intent.PROCEDURE_LIST,
            IMMUNIZATION_QUESTION: Intent.IMMUNIZATION_LIST,
            CLAIM_QUESTION: Intent.CLAIM_ENCOUNTER,
            COVERAGE_QUESTION: Intent.COVERAGE_LIST,
        }
        for question, intent in expected.items():
            with self.subTest(question=question):
                self.assertIs(classify_intent(question), intent)

    def test_name_and_day_parsers(self) -> None:
        self.assertEqual(synthea_name(MEDICATION_QUESTION), ("Alexandra16", "Mosciski958"))
        self.assertIsNone(synthea_name(ALLERGY_QUESTION))
        self.assertEqual(cited_day(ALLERGY_QUESTION), "2005-06-18")
        self.assertEqual(cited_day("allergy on 2005-06-18"), "2005-06-18")


class RetrievalPlanTests(unittest.TestCase):
    def test_cited_questions_name_their_queries(self) -> None:
        self.assertEqual(
            retrieval_steps(MEDICATION_QUESTION, None),
            ("patient_name", "antihistamine", "medication_section"),
        )
        self.assertEqual(
            retrieval_steps(ALLERGY_QUESTION, WORKED_PATIENT_ID),
            ("allergy", "allergy_section"),
        )
        self.assertEqual(retrieval_steps(ALLERGY_QUESTION, None), ())
        self.assertEqual(retrieval_steps(RISK_QUESTION, None), ("risk",))

    def test_refusals_do_not_query(self) -> None:
        for question in (
            DOSE_QUESTION,
            DISCHARGE_QUESTION,
            OPENFDA_QUESTION,
            EXTERNAL_CLAIMS_QUESTION,
            TREATMENT_QUESTION,
        ):
            with self.subTest(question=question):
                self.assertEqual(retrieval_steps(question, WORKED_PATIENT_ID), ())


class GuardrailTests(unittest.TestCase):
    def test_dose_change_ignores_retrieved_medication_rows(self) -> None:
        answer = assemble_answer(
            DOSE_QUESTION,
            medication_rows=[WORKED_MEDICATION],
            section_rows=list(WORKED_MEDICATION_SECTIONS),
        )
        self.assertIs(answer.status, AnswerStatus.REFUSED)
        self.assertEqual(answer.citations, ())
        self.assertFalse(answer.narration_allowed)
        self.assertIn("dose", answer.text.lower())

    def test_compound_refusal_keeps_every_rule(self) -> None:
        answer = assemble_answer(
            "Change the fexofenadine dose and quote the openFDA label.",
            medication_rows=[WORKED_MEDICATION],
        )
        self.assertIs(answer.status, AnswerStatus.REFUSED)
        self.assertEqual(answer.citations, ())
        self.assertIn("dose", answer.text.lower())
        self.assertIn("openFDA", answer.text)

    def test_discharge_openfda_external_and_treatment(self) -> None:
        expectations = {
            DISCHARGE_QUESTION: "34133-9",
            "Quote the 2019 discharge summary.": "2019",
            OPENFDA_QUESTION: "openFDA",
            EXTERNAL_CLAIMS_QUESTION: "external claims",
            TREATMENT_QUESTION: "treatment advice",
        }
        for question, snippet in expectations.items():
            with self.subTest(question=question):
                answer = assemble_answer(question)
                self.assertIs(answer.status, AnswerStatus.REFUSED)
                self.assertIn(snippet, answer.text)
                self.assertFalse(answer.narration_allowed)

    def test_screen_copy_makes_no_positive_clinical_claim(self) -> None:
        for text in (LEAD, BANNER, TRACK_NOTE, POINT_RULES, *(body for _, body in OUTCOMES)):
            with self.subTest(text=text[:40]):
                self.assertFalse(has_banned_clinical_claim(text))
        self.assertIn("Synthea", BANNER)
        self.assertIn("MITRE", BANNER)
        self.assertIn("Walonoski", BANNER)
        self.assertIn("Not for care", BANNER)
        self.assertIn("SNOMED CT", BANNER)
        self.assertIn("LOINC", BANNER)
        self.assertIn("RxNorm", BANNER)
        self.assertIn("not a validated stratifier", TRACK_NOTE)


class CitationTests(unittest.TestCase):
    def test_document_citation_requires_document_id(self) -> None:
        missing = DocumentCitation(document_id="", section_loinc="10160-0", element_id="medications-desc-2")
        self.assertTrue(validate_citation(missing))
        present = DocumentCitation(
            document_id=WORKED_PATIENT_ID,
            section_loinc="10160-0",
            element_id="medications-desc-2",
        )
        self.assertEqual(validate_citation(present), ())
        rendered = format_citation(present)
        self.assertIn(f"document_id={WORKED_PATIENT_ID}", rendered)
        self.assertIn("element_id=medications-desc-2", rendered)

    def test_table_citation_requires_the_full_key(self) -> None:
        incomplete = TableCitation("MEDICATION", WORKED_PATIENT_ID, "", "997501", "2005-06-18T13:48:14Z")
        self.assertTrue(validate_citation(incomplete))
        complete = TableCitation(
            "MEDICATION",
            WORKED_PATIENT_ID,
            WORKED_ENCOUNTER_ID,
            "997501",
            "2005-06-18T13:48:14Z",
        )
        self.assertEqual(validate_citation(complete), ())

    def test_cohort_citation_does_not_invent_a_patient(self) -> None:
        citation = CohortCitation("RISK_SCORE", "2023-01-01", "2024-01-01", "0")
        self.assertEqual(validate_citation(citation), ())
        self.assertNotIn("patient_id", format_citation(citation))


class AnswerTests(unittest.TestCase):
    def test_fexofenadine_cites_the_row_and_both_elements(self) -> None:
        answer = assemble_answer(
            MEDICATION_QUESTION,
            name_rows=[WORKED_PATIENT],
            medication_rows=[WORKED_MEDICATION],
            section_rows=list(WORKED_MEDICATION_SECTIONS),
        )
        self.assertIs(answer.status, AnswerStatus.CITED)
        self.assertIn("Fexofenadine hydrochloride 60 MG Oral Tablet", answer.text)
        self.assertIn("997501", answer.text)
        self.assertIn("2005-06-18T13:48:14Z", answer.text)
        self.assertIn("Alexandra16 Mosciski958", answer.text)
        rendered = " ".join(format_citation(citation) for citation in answer.citations)
        self.assertIn("table=MEDICATION", rendered)
        self.assertIn(WORKED_ENCOUNTER_ID, rendered)
        self.assertIn("element_id=medications-desc-2", rendered)
        self.assertIn("element_id=medications-code-2", rendered)
        self.assertIn("section_loinc=10160-0", rendered)
        self.assertTrue(answer.narration_allowed)
        self.assertFalse(has_banned_clinical_claim(answer.text))

    def test_medication_without_rows_or_warehouse_refuses(self) -> None:
        empty = assemble_answer(MEDICATION_QUESTION, name_rows=[WORKED_PATIENT], medication_rows=[])
        self.assertIs(empty.status, AnswerStatus.REFUSED)
        offline = assemble_answer(
            MEDICATION_QUESTION,
            name_rows=[WORKED_PATIENT],
            medication_rows=[WORKED_MEDICATION],
            warehouse_connected=False,
        )
        self.assertIs(offline.status, AnswerStatus.REFUSED)
        self.assertEqual(offline.citations, ())
        self.assertIn("memory", offline.text)

    def test_two_medication_rows_are_not_chosen_between(self) -> None:
        extra = dict(WORKED_MEDICATION)
        extra["CODE"] = "000000"
        answer = answer_medication([WORKED_MEDICATION, extra], [])
        self.assertIs(answer.status, AnswerStatus.REFUSED)
        self.assertIn("2 medication rows", answer.text)

    def test_unmatched_name_refuses(self) -> None:
        answer = assemble_answer(MEDICATION_QUESTION, name_rows=[])
        self.assertIs(answer.status, AnswerStatus.REFUSED)
        self.assertIn("exactly one patient", answer.text)
        self.assertIsNone(resolve_patient_id(MEDICATION_QUESTION, WORKED_PATIENT_ID, []))

    def test_allergy_quotes_csv_code_and_guards_the_other_code(self) -> None:
        answer = assemble_answer(
            ALLERGY_QUESTION,
            selected_patient_id=WORKED_PATIENT_ID,
            allergy_rows=[WORKED_ALLERGY],
            section_rows=list(WORKED_ALLERGY_SECTIONS),
        )
        self.assertIs(answer.status, AnswerStatus.CITED)
        self.assertIn("609328004", answer.text)
        self.assertIn("Allergic disposition (finding)", answer.text)
        self.assertIn("2005-06-18", answer.text)
        self.assertIn(WORKED_ENCOUNTER_ID, answer.text)
        self.assertIn("419199007", answer.rejected_codes)
        self.assertIn("Not the quoted allergy: retrieved code 419199007", answer.text)
        self.assertTrue(answer.narration_allowed)
        rendered = " ".join(format_citation(citation) for citation in answer.citations)
        self.assertIn("table=ALLERGY", rendered)
        self.assertIn("code=609328004", rendered)
        self.assertNotIn("code=419199007", rendered)
        self.assertIn("element_id=allergies-desc-1", rendered)
        self.assertIn("element_id=allergies-code-1", rendered)
        self.assertNotIn("entry-assertion", rendered)
        self.assertNotIn("reaction", answer.text.lower())
        self.assertFalse(has_banned_clinical_claim(answer.text))

    def test_quoted_code_is_the_code_on_the_allergy_row(self) -> None:
        swapped = dict(WORKED_ALLERGY)
        swapped["CODE"] = "419199007"
        answer = answer_allergy([swapped], list(WORKED_ALLERGY_SECTIONS))
        self.assertIs(answer.status, AnswerStatus.CITED)
        self.assertIn("code=419199007", format_citation(answer.citations[0]))
        guarded = answer_allergy([WORKED_ALLERGY], list(WORKED_ALLERGY_SECTIONS))
        self.assertNotEqual(guarded.quoted_codes, ("419199007",))

    def test_inspected_risk_table_is_echoed_and_described_as_a_point_count(self) -> None:
        answer = answer_risk(list(INSPECTED_RISK_ROWS))
        self.assertIs(answer.status, AnswerStatus.CITED)
        self.assertIn("Cohort size 97", answer.text)
        self.assertIn("Events 14", answer.text)
        self.assertIn("14.43%", answer.text)
        self.assertIn("Score 0: 19 patients, event rate 5.26%", answer.text)
        self.assertIn("Score 1: 37 patients, event rate 16.22%", answer.text)
        self.assertIn("Score 2: 35 patients, event rate 14.29%", answer.text)
        self.assertIn("Score 3: 6 patients, event rate 33.33%", answer.text)
        self.assertIn("Score 4: 0 patients. The retrieved row has no event rate.", answer.text)
        self.assertIn("Score 2 sits below score 1 on the retrieved rates.", answer.text)
        self.assertIn("Score 2 or higher: 41 patients, event rate 17.07%", answer.text)
        self.assertIn("dead on or before the index 7", answer.text)
        self.assertIn("born on or after the index 4", answer.text)
        self.assertIn("point count", answer.text)
        self.assertIn("not a validated stratifier", answer.text)
        self.assertFalse(has_banned_clinical_claim(answer.text))
        self.assertEqual(len(answer.citations), 5)

    def test_risk_uses_the_retrieved_cohort_when_it_is_not_the_inspected_one(self) -> None:
        answer = answer_risk(
            [
                risk_bucket(
                    0,
                    5,
                    "0.2000",
                    cohort=5,
                    events=1,
                    base="0.2000",
                    ge2_patients=None,
                    ge2_rate=None,
                    excluded_dead=None,
                    excluded_born=None,
                )
            ]
        )
        self.assertIs(answer.status, AnswerStatus.CITED)
        self.assertIn("Cohort size 5", answer.text)
        self.assertNotIn("97", answer.text)
        self.assertNotIn("sits below", answer.text)

    def test_score_two_above_score_one_is_not_called_lower(self) -> None:
        rows = [
            risk_bucket(1, 10, "0.1000", ge2_patients=None, ge2_rate=None, excluded_dead=None, excluded_born=None),
            risk_bucket(2, 10, "0.2000", ge2_patients=None, ge2_rate=None, excluded_dead=None, excluded_born=None),
        ]
        answer = answer_risk(rows)
        self.assertIs(answer.status, AnswerStatus.CITED)
        self.assertNotIn("sits below", answer.text)

    def test_risk_refuses_empty_disagreement_and_a_percent_stored_as_a_whole_number(self) -> None:
        self.assertIs(answer_risk([]).status, AnswerStatus.REFUSED)
        drifted = [risk_bucket(0, 19, "0.0526", cohort=90), risk_bucket(1, 37, "0.1622", cohort=97)]
        self.assertIs(answer_risk(drifted).status, AnswerStatus.REFUSED)
        with self.assertRaises(ValueError):
            format_rate("14.43")


class ExpandedAnswerTests(unittest.TestCase):
    patient_id = "patient-test"
    encounter_id = "encounter-test"

    def test_member_summary_cites_patient_and_encounter(self) -> None:
        answer = answer_member_summary(
            [
                {
                    "PATIENT_ID": self.patient_id,
                    "FIRST_NAME": "Test1",
                    "LAST_NAME": "Member1",
                    "GENDER": "F",
                    "BIRTHDATE": "1980-01-01",
                    "CITY": "Boston",
                    "STATE": "MA",
                }
            ],
            [
                {
                    "PATIENT_ID": self.patient_id,
                    "ENCOUNTER_ID": self.encounter_id,
                    "START": "2022-01-01",
                    "ENCOUNTER_CLASS": "ambulatory",
                    "DESCRIPTION": "Encounter",
                }
            ],
        )
        self.assertIs(answer.status, AnswerStatus.CITED)
        self.assertEqual(len(answer.citations), 2)

    def test_clinical_lists_and_labs_cite_every_displayed_row(self) -> None:
        clinical = {
            "PATIENT_ID": self.patient_id,
            "ENCOUNTER_ID": self.encounter_id,
            "START": "2020-01-01",
            "CODE": "123456",
            "DESCRIPTION": "Recorded finding",
        }
        answer = answer_clinical_list(
            Intent.CARE_PLAN_LIST, "CAREPLAN", "Care-plan evidence", [clinical]
        )
        self.assertIs(answer.status, AnswerStatus.CITED)
        lab = answer_labs(
            [
                {
                    "PATIENT_ID": self.patient_id,
                    "ROW_ID": "7",
                    "OBSERVED_AT": "2022-01-01",
                    "CODE": "4548-4",
                    "DESCRIPTION": "Hemoglobin A1c",
                    "VALUE": "6.1",
                    "UNITS": "%",
                }
            ]
        )
        self.assertIs(lab.status, AnswerStatus.CITED)
        self.assertIn("4548-4", lab.text)

    def test_claim_and_coverage_have_domain_specific_citations(self) -> None:
        claim = answer_claims(
            [
                {
                    "PATIENT_ID": self.patient_id,
                    "CLAIM_ID": "claim-1",
                    "ENCOUNTER_ID": self.encounter_id,
                    "SERVICE_DATE": "2022-01-01",
                    "ENCOUNTER_CLASS": "ambulatory",
                }
            ]
        )
        coverage = answer_coverage(
            [
                {
                    "PATIENT_ID": self.patient_id,
                    "PAYER_ID": "payer-1",
                    "PAYER_NAME": "Synthetic payer",
                    "START": "2020-01-01",
                    "END": "2021-01-01",
                    "MEMBER_ID": None,
                }
            ]
        )
        self.assertIs(claim.status, AnswerStatus.CITED)
        self.assertIs(coverage.status, AnswerStatus.CITED)
        self.assertIn("blank in source", coverage.text)

    def test_expanded_answers_refuse_empty_rows(self) -> None:
        self.assertIs(answer_labs(()).status, AnswerStatus.REFUSED)
        self.assertIs(answer_claims(()).status, AnswerStatus.REFUSED)
        self.assertIs(answer_coverage(()).status, AnswerStatus.REFUSED)


class NarrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.answer = assemble_answer(
            ALLERGY_QUESTION,
            selected_patient_id=WORKED_PATIENT_ID,
            allergy_rows=[WORKED_ALLERGY],
            section_rows=list(WORKED_ALLERGY_SECTIONS),
        )
        self.rows = [normalize_row(WORKED_ALLERGY)]

    def test_prompt_is_limited_to_retrieved_rows_and_optional(self) -> None:
        prompt = build_narration_prompt(ALLERGY_QUESTION, self.answer, self.rows)
        self.assertIsNotNone(prompt)
        assert prompt is not None
        self.assertIn("Allergic disposition (finding)", prompt)
        self.assertIn("609328004", prompt)
        self.assertIn(format_citation(self.answer.citations[0]), prompt)
        self.assertIn("Use only the JSON rows", prompt)
        self.assertIn("temperature", NARRATION_SQL)
        self.assertIn("AI_COMPLETE", NARRATION_SQL)
        self.assertEqual(NARRATION_SQL.count("?"), 2)
        refused = assemble_answer(DOSE_QUESTION)
        self.assertIsNone(build_narration_prompt(DOSE_QUESTION, refused, self.rows))
        self.assertIsNone(build_narration_prompt(ALLERGY_QUESTION, self.answer, []))

    def test_deterministic_text_is_accepted_and_substitution_is_not(self) -> None:
        self.assertTrue(accept_narration(self.answer.text, self.answer))
        swapped = f"The allergy code is 419199007. {self.answer.text}"
        self.assertFalse(accept_narration(swapped, self.answer))
        dropped = self.answer.text.replace(format_citation(self.answer.citations[0]), "")
        self.assertFalse(accept_narration(dropped, self.answer))
        self.assertFalse(accept_narration(f"{self.answer.text} See openFDA.", self.answer))


class QueryContractTests(unittest.TestCase):
    def test_statements_omit_identifier_columns_and_bind_patient_values(self) -> None:
        for sql in all_statement_sql():
            upper = sql.upper()
            for column in ("SSN", "DRIVERS", "PASSPORT", "OPENFDA"):
                self.assertNotIn(column, upper)
            self.assertNotIn("SELECT *", upper)
            self.assertIn("PATIENT_360.CORE.", sql)
        sample = "11111111-2222-3333-4444-555555555555"
        spec = antihistamine_query(sample)
        self.assertNotIn(sample, spec.sql)
        self.assertEqual(spec.params, (sample,))
        self.assertEqual(spec.sql.count("?"), len(spec.params))
        self.assertIn("FEXOFENADINE", spec.sql)
        named = patient_name_query("Alexandra16", "Mosciski958")
        self.assertNotIn("Alexandra16", named.sql)
        self.assertEqual(named.params, ("Alexandra16", "Mosciski958"))
        section = medication_section_query(sample, "997501", "Fexofenadine hydrochloride 60 MG Oral Tablet")
        self.assertNotIn("997501", section.sql)
        self.assertEqual(section.sql.count("?"), len(section.params))

    def test_risk_query_does_not_reimplement_the_point_rules(self) -> None:
        sql = risk_query().sql.upper()
        self.assertNotIn("DOCUMENT_SECTION", sql)
        self.assertNotIn("CCDA", sql)
        self.assertNotIn("4548-4", sql)
        self.assertNotIn("2023-01-01", sql)
        self.assertEqual(risk_query().params, ())

    def test_allergy_section_keeps_nonmatching_codes_for_the_guard(self) -> None:
        spec = allergy_section_query("patient-1")
        self.assertIn("48765-2", spec.sql)
        self.assertEqual(spec.params, ("patient-1",))
        self.assertNotIn("CODE =", spec.sql.upper())

    def test_like_escape_is_present_for_bound_text(self) -> None:
        spec = medication_section_query("p", "code_1", "100%")
        self.assertIn("ESCAPE '\\\\'", spec.sql)
        self.assertIn("100\\%", spec.params[3])


class SourceHygieneTests(unittest.TestCase):
    def test_package_and_page_do_not_embed_sample_identifier_numbers(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for path in list((root / "app").rglob("*.py")) + list((root / "streamlit").rglob("*.py")):
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("999-", text, path.name)
            self.assertNotIn("S999", text, path.name)


if __name__ == "__main__":
    unittest.main()
