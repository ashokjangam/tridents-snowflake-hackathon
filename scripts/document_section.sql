-- RAW.DOCUMENT_SECTION for the Synthea C-CDA parse.
-- Run through Invoke-Patient360Load.ps1. Tokens are replaced from config.
-- This file has no account credentials.
-- code is the narrative-table code. rejected_codes holds assertion and
-- wrapper codes (allergy 419199007, generic Condition 64572001) and is not the quote.

CREATE DATABASE IF NOT EXISTS __DATABASE__;
CREATE SCHEMA IF NOT EXISTS __DATABASE__.__SCHEMA__;

CREATE OR REPLACE FILE FORMAT __DATABASE__.__SCHEMA__.__FILE_FORMAT__
  TYPE = CSV
  PARSE_HEADER = TRUE
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  ESCAPE_UNENCLOSED_FIELD = NONE
  EMPTY_FIELD_AS_NULL = FALSE
  TRIM_SPACE = FALSE
  ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE
  ENCODING = 'UTF8'
  REPLACE_INVALID_CHARACTERS = FALSE
  COMMENT = 'Quoted CSV from the local C-CDA parser. Newlines stay inside quoted fields.';

CREATE OR REPLACE TABLE __DATABASE__.__SCHEMA__.__TABLE__ (
  document_id VARCHAR,
  patient_id VARCHAR,
  effective_time VARCHAR,
  section_loinc VARCHAR,
  section_title VARCHAR,
  element_id VARCHAR,
  text VARCHAR,
  code VARCHAR,
  code_system VARCHAR,
  source_file VARCHAR,
  element_role VARCHAR,
  row_start VARCHAR,
  row_stop VARCHAR,
  row_value VARCHAR,
  narrative_code VARCHAR,
  narrative_system_uri VARCHAR,
  code_system_name VARCHAR,
  structured_code VARCHAR,
  structured_code_system VARCHAR,
  rejected_codes VARCHAR,
  quote_safe VARCHAR,
  csv_table VARCHAR,
  csv_match VARCHAR,
  csv_encounter VARCHAR,
  csv_start VARCHAR,
  ordinal NUMBER(10, 0)
)
COMMENT = 'Synthea C-CDA narrative cells. Citation grain is (document_id, element_id). Quote code, not rejected_codes.';

CREATE STAGE IF NOT EXISTS __DATABASE__.__SCHEMA__.__STAGE__
  FILE_FORMAT = __DATABASE__.__SCHEMA__.__FILE_FORMAT__
  COMMENT = 'Local C-CDA parse output. No secrets.';
