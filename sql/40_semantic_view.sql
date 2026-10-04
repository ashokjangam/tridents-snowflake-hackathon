-- Semantic view CORE.SEM_MEMBER.
-- Run after 30_core_views.sql.
-- Syntax follows the current Snowflake CREATE SEMANTIC VIEW command:
-- TABLES, RELATIONSHIPS, FACTS, DIMENSIONS, METRICS, COMMENT, AI_SQL_GENERATION, COPY GRANTS.
-- CREATE OR ALTER SEMANTIC VIEW is a May 2026 preview and is not required here.
-- This object is queried with SEMANTIC_VIEW(), not with SELECT *.
-- The six demo questions are answered from CORE views in tests/demo_questions.sql.
-- If this command is rejected, skip this file. Do not rename a relational view to SEM_MEMBER.
-- Re-run 90_roles_grants.sql after the first create. Later re-runs use COPY GRANTS.
--
-- Metrics stay on one logical table so a fact with both a patient and an encounter
-- relationship does not make a metric path ambiguous.
-- Medication and observation business keys are not unique, so those primary keys are the load row number.
-- Allergy is included because the demo must quote the CSV allergy code.
-- No deterioration probability, no openFDA label, and no dose recommendation.

USE DATABASE PATIENT_360;
USE SCHEMA CORE;
USE WAREHOUSE PATIENT_360_WH;

CREATE OR REPLACE SEMANTIC VIEW PATIENT_360.CORE.SEM_MEMBER
  TABLES (
    patient AS PATIENT_360.CORE.PATIENT
      PRIMARY KEY (PATIENT_ID)
      WITH SYNONYMS = ('member', 'beneficiary', 'patient')
      COMMENT = 'Simulated Synthea person. SSN, drivers license, and passport are not in this model.',
    encounter AS PATIENT_360.CORE.ENCOUNTER
      PRIMARY KEY (ENCOUNTER_ID)
      COMMENT = 'Encounter. The claim appointment id points here.',
    condition AS PATIENT_360.CORE.CONDITION
      PRIMARY KEY (PATIENT_ID, ENCOUNTER_ID, CODE, START_DATE)
      COMMENT = 'Condition. Code system is SNOMED CT. Active-condition counts include findings and situations.',
    medication AS PATIENT_360.CORE.MEDICATION
      PRIMARY KEY (SOURCE_FILE_ROW_NUMBER)
      COMMENT = 'Medication dispense. Code is RxNorm. Not a dose order. Patient, encounter, code, and start are not unique.',
    observation AS PATIENT_360.CORE.OBSERVATION
      PRIMARY KEY (SOURCE_FILE_ROW_NUMBER)
      COMMENT = 'Observation. Code 4548-4 is Hemoglobin A1c. Some rows have no encounter.',
    claim AS PATIENT_360.CORE.CLAIM
      PRIMARY KEY (CLAIM_ID)
      COMMENT = 'Claim. Appointment id is the encounter id. Primary payer id is a payer id when filled, not a member id.',
    claim_line AS PATIENT_360.CORE.CLAIM_LINE
      PRIMARY KEY (CLAIM_LINE_ID)
      COMMENT = 'Claim line. Notes are the charge description, not a clinical document. Amount is not a patient balance.',
    coverage_span AS PATIENT_360.CORE.PAYER_TRANSITION
      PRIMARY KEY (SOURCE_FILE_ROW_NUMBER)
      COMMENT = 'Coverage span. Member id is not the patient key and is empty on many spans.',
    document_section AS PATIENT_360.CORE.DOCUMENT_SECTION
      PRIMARY KEY (DOCUMENT_ID, ELEMENT_ID)
      COMMENT = 'Parsed C-CDA cell. Document id equals patient id. Element ids restart across documents.',
    allergy AS PATIENT_360.CORE.ALLERGY
      PRIMARY KEY (PATIENT_ID, ENCOUNTER_ID, CODE, START_DATE)
      COMMENT = 'Allergy row. Quote this code. Do not substitute a different assertion code from the same document entry.',
    risk_cohort AS PATIENT_360.CORE.RISK_COHORT
      PRIMARY KEY (PATIENT_ID)
      COMMENT = 'Frozen point count. Not a probability, not a validated model, and not a care recommendation.'
  )
  RELATIONSHIPS (
    encounter_to_patient AS
      encounter (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    condition_to_patient AS
      condition (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    condition_to_encounter AS
      condition (ENCOUNTER_ID) REFERENCES encounter (ENCOUNTER_ID),
    medication_to_patient AS
      medication (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    medication_to_encounter AS
      medication (ENCOUNTER_ID) REFERENCES encounter (ENCOUNTER_ID),
    observation_to_patient AS
      observation (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    observation_to_encounter AS
      observation (ENCOUNTER_ID) REFERENCES encounter (ENCOUNTER_ID),
    claim_to_patient AS
      claim (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    claim_to_encounter AS
      claim (APPOINTMENT_ID) REFERENCES encounter (ENCOUNTER_ID),
    claim_line_to_claim AS
      claim_line (CLAIM_ID) REFERENCES claim (CLAIM_ID),
    coverage_to_patient AS
      coverage_span (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    document_to_patient AS
      document_section (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    allergy_to_patient AS
      allergy (PATIENT_ID) REFERENCES patient (PATIENT_ID),
    allergy_to_encounter AS
      allergy (ENCOUNTER_ID) REFERENCES encounter (ENCOUNTER_ID),
    risk_to_patient AS
      risk_cohort (PATIENT_ID) REFERENCES patient (PATIENT_ID)
  )
  FACTS (
    encounter.base_encounter_cost AS base_encounter_cost,
    encounter.total_claim_cost AS total_claim_cost,
    medication.total_cost AS total_cost
      COMMENT = 'Historical dispense total. Not an instruction to change a dose.',
    claim_line.line_amount AS amount
      COMMENT = 'Line amount. Do not add charge rows and payment rows into a patient balance.',
    risk_cohort.event_flag AS event_flag
      COMMENT = '1 when the cohort patient had an emergency or inpatient encounter in 2023. Label only.'
  )
  DIMENSIONS (
    patient.patient_id AS patient_id
      WITH SYNONYMS = ('member id', 'beneficiary id')
      COMMENT = 'Patient UUID. This is the member key.',
    patient.first_name AS first_name,
    patient.last_name AS last_name,
    patient.gender AS gender,
    patient.birthdate AS birthdate,
    patient.deathdate AS deathdate,
    patient.city AS city,
    patient.state AS state,
    encounter.encounter_id AS encounter_id,
    encounter.encounter_patient_id AS patient_id,
    encounter.encounter_start AS start_ts,
    encounter.encounter_class AS encounter_class,
    encounter.encounter_code AS code,
    encounter.encounter_description AS description,
    condition.condition_code AS code
      COMMENT = 'SNOMED CT code.',
    condition.condition_description AS description,
    condition.condition_start AS start_date,
    condition.condition_patient_id AS patient_id,
    condition.condition_encounter_id AS encounter_id,
    medication.medication_code AS code
      WITH SYNONYMS = ('rxnorm', 'rxcui')
      COMMENT = 'RxNorm code. Not a dose order.',
    medication.medication_description AS description,
    medication.medication_start AS start_ts,
    medication.medication_patient_id AS patient_id,
    medication.medication_encounter_id AS encounter_id,
    observation.observation_code AS code
      COMMENT = 'LOINC-style code. 4548-4 is Hemoglobin A1c.',
    observation.observation_description AS description,
    observation.observation_value AS value_text,
    observation.observation_time AS observation_ts,
    observation.observation_category AS category,
    observation.observation_patient_id AS patient_id,
    observation.observation_encounter_id AS encounter_id,
    claim.claim_id AS claim_id,
    claim.claim_patient_id AS patient_id,
    claim.claim_appointment_id AS appointment_id
      COMMENT = 'Encounter id for this claim.',
    claim.claim_diagnosis_1 AS diagnosis_1,
    claim.claim_primary_payer_id AS primary_payer_id
      COMMENT = 'Payer id when filled. Not a member id.',
    claim_line.claim_line_id AS claim_line_id,
    claim_line.claim_line_claim_id AS claim_id,
    claim_line.claim_line_procedure_code AS procedure_code,
    claim_line.claim_line_notes AS notes
      COMMENT = 'Charge description. Not a clinical document.',
    coverage_span.coverage_member_id AS member_id
      COMMENT = 'Span id. Empty on many rows. Not the patient key.',
    coverage_span.coverage_patient_id AS patient_id,
    coverage_span.coverage_payer_id AS payer_id,
    coverage_span.coverage_start AS start_ts,
    coverage_span.coverage_end AS end_ts,
    document_section.document_id AS document_id
      COMMENT = 'Same value as patient_id on this export.',
    document_section.element_id AS element_id
      COMMENT = 'Unique only inside one document.',
    document_section.section_loinc AS section_loinc,
    document_section.section_title AS section_title,
    document_section.section_text AS text,
    document_section.section_code AS code,
    document_section.document_patient_id AS patient_id,
    allergy.allergy_code AS code
      COMMENT = 'CSV match. For the worked patient this is 609328004, not 419199007.',
    allergy.allergy_description AS description,
    allergy.allergy_start AS start_date,
    allergy.allergy_patient_id AS patient_id,
    allergy.allergy_encounter_id AS encounter_id,
    risk_cohort.point_total AS point_total
      COMMENT = 'Frozen point count from 0 to 4. Not a probability.',
    risk_cohort.point_age_ge_65 AS point_age_ge_65,
    risk_cohort.point_prior_acute_encounter AS point_prior_acute_encounter,
    risk_cohort.point_active_conditions_ge_8 AS point_active_conditions_ge_8,
    risk_cohort.point_last_a1c_ge_6_5 AS point_last_a1c_ge_6_5,
    risk_cohort.age_years_at_index AS age_years_at_index,
    risk_cohort.risk_patient_id AS patient_id
  )
  METRICS (
    patient.member_count AS COUNT(patient_id)
      COMMENT = 'Count of simulated patients.',
    encounter.encounter_count AS COUNT(encounter_id)
      COMMENT = 'Count of encounters.',
    claim.claim_count AS COUNT(claim_id)
      COMMENT = 'Count of claims.',
    medication.medication_row_count AS COUNT(source_file_row_number)
      COMMENT = 'Medication rows. Not a count of distinct drugs.',
    risk_cohort.cohort_patient_count AS COUNT(patient_id)
      COMMENT = 'Frozen cohort size. Not a predicted risk.',
    risk_cohort.acute_event_count AS SUM(event_flag)
      COMMENT = 'Count of cohort patients with an emergency or inpatient encounter in 2023.'
  )
  COMMENT = 'Member semantic model for the Synthea demo. Not for care. The point count is not a probability, not a validated model, and not a care recommendation. No openFDA label and no dose recommendation.'
  AI_SQL_GENERATION '
These rows are MITRE Synthea simulations for a software demo and are not for clinical care.
Member, patient, and beneficiary are the same person. Use patient_id.
Cite a medication, condition, or allergy with patient_id, encounter_id, code, and start.
Cite a document cell with document_id, section_loinc, and element_id. Element ids restart across documents, so document_id is required.
For patient 37549f60-b5a3-69cd-dea6-5a71c4bc23cf the antihistamine is RxNorm 997501, Fexofenadine hydrochloride 60 MG Oral Tablet.
The allergy code that matches the structured allergy row is SNOMED 609328004. Do not replace it with 419199007.
The risk figures are a frozen point count for index date 2023-01-01. Score 2 is below score 1. Do not call the point count a probability, a validated model, or a care recommendation.
Refuse a dose change, a treatment recommendation, a 2019 discharge summary, and an openFDA label. Those sources are not in this view.
SSN, drivers license, and passport are not in this model.
Coverage member_id is not the patient key.
Claim primary_payer_id is a payer id when it is filled.
Prefer the direct patient relationship when a fact also has an encounter relationship.
'
  COPY GRANTS;
