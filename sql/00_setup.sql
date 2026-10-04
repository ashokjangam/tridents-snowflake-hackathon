-- Patient 360 database, warehouse, schemas, file formats, and internal stage.
-- Idempotent. Re-running keeps the XS warehouse and does not store credentials.
-- Run first, as ACCOUNTADMIN or another role that can create a database, warehouse, and schema:
--   snow sql -f patient-360/sql/00_setup.sql --connection <connection>
-- For the complete load, use scripts/Invoke-Patient360Load.ps1; it expands the local
-- file URI tokens in the 20_load.sql template before executing the remaining scripts.
--
-- One database, PATIENT_360. One XS warehouse. No external stage and no secrets.
-- Source: MITRE Synthea paired CSV and C-CDA sample. Simulated patients, not for care.
-- Citation: Walonoski et al., JAMIA 2018, https://doi.org/10.1093/jamia/ocx079

CREATE DATABASE IF NOT EXISTS PATIENT_360
    COMMENT = 'Synthea patient and member 360 demo. MITRE simulations, not for care. Walonoski et al., JAMIA 2018.';

ALTER DATABASE PATIENT_360 SET
    COMMENT = 'Synthea patient and member 360 demo. MITRE simulations, not for care. Walonoski et al., JAMIA 2018. No second database.';

CREATE WAREHOUSE IF NOT EXISTS PATIENT_360_WH
    WAREHOUSE_SIZE = XSMALL
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'XS warehouse for the Synthea Patient 360 demo.';

ALTER WAREHOUSE PATIENT_360_WH SET
    WAREHOUSE_SIZE = XSMALL
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    COMMENT = 'XS warehouse for the Synthea Patient 360 demo. Do not resize.';

CREATE SCHEMA IF NOT EXISTS PATIENT_360.RAW
    COMMENT = 'Loaded Synthea files and parsed C-CDA cells, including SSN, DRIVERS, and PASSPORT.';

CREATE SCHEMA IF NOT EXISTS PATIENT_360.CORE
    COMMENT = 'Analyst views. SSN, DRIVERS, and PASSPORT are omitted. City, state, and the patient UUID remain.';

ALTER SCHEMA PATIENT_360.RAW SET
    COMMENT = 'Loaded Synthea files and parsed C-CDA cells, including SSN, DRIVERS, and PASSPORT. The analyst role has no SELECT here.';

ALTER SCHEMA PATIENT_360.CORE SET
    COMMENT = 'Analyst views over RAW. SSN, DRIVERS, and PASSPORT are omitted. Not for care.';

USE DATABASE PATIENT_360;
USE SCHEMA RAW;
USE WAREHOUSE PATIENT_360_WH;

CREATE OR REPLACE FILE FORMAT PATIENT_360.RAW.FF_SYNTHEA_CSV
    TYPE = CSV
    COMPRESSION = AUTO
    FIELD_DELIMITER = ','
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    ESCAPE_UNENCLOSED_FIELD = NONE
    TRIM_SPACE = FALSE
    ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE
    EMPTY_FIELD_AS_NULL = TRUE
    NULL_IF = ('')
    SKIP_BLANK_LINES = FALSE
    DATE_FORMAT = 'YYYY-MM-DD'
    TIMESTAMP_FORMAT = 'YYYY-MM-DD"T"HH24:MI:SS"Z"'
    ENCODING = 'UTF8'
    COMMENT = 'Synthea CSV. Dates are YYYY-MM-DD. Timestamps keep the source clock digits; Z is a format marker.';

CREATE OR REPLACE FILE FORMAT PATIENT_360.RAW.FF_DOCUMENT_CSV
    TYPE = CSV
    COMPRESSION = AUTO
    FIELD_DELIMITER = ','
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    ESCAPE_UNENCLOSED_FIELD = NONE
    TRIM_SPACE = FALSE
    ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE
    EMPTY_FIELD_AS_NULL = TRUE
    NULL_IF = ('')
    SKIP_BLANK_LINES = FALSE
    REPLACE_INVALID_CHARACTERS = TRUE
    ENCODING = 'UTF8'
    COMMENT = 'Parsed C-CDA section CSV. Quoted fields. Doubled quotes escape a quote. Not a document blob.';

CREATE STAGE IF NOT EXISTS PATIENT_360.RAW.STG_CSV
    FILE_FORMAT = PATIENT_360.RAW.FF_SYNTHEA_CSV
    COMMENT = 'Internal stage for local Synthea CSV and the parsed section CSV. No external URL and no credentials.';

ALTER STAGE PATIENT_360.RAW.STG_CSV SET
    FILE_FORMAT = PATIENT_360.RAW.FF_SYNTHEA_CSV;

ALTER STAGE PATIENT_360.RAW.STG_CSV SET
    COMMENT = 'Internal stage. Prefix csv/<table>/ holds one Synthea file. Prefix parsed/document_section/ holds the parsed C-CDA CSV.';
