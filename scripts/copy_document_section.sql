-- Load the parser CSV after snow stage copy. Tokens are replaced from config.

COPY INTO __DATABASE__.__SCHEMA__.__TABLE__
  FROM @__DATABASE__.__SCHEMA__.__STAGE__/document_section
  FILE_FORMAT = (FORMAT_NAME = '__DATABASE__.__SCHEMA__.__FILE_FORMAT__')
  MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
  ON_ERROR = ABORT_STATEMENT
  PURGE = FALSE;

SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT document_id) AS document_count,
  COUNT(DISTINCT patient_id) AS patient_count,
  SUM(IFF(document_id = patient_id, 0, 1)) AS identity_mismatch_rows,
  COUNT_IF(element_role = 'description' AND csv_table = 'medications') AS medication_desc,
  COUNT_IF(element_role = 'description' AND csv_table = 'allergies') AS allergy_desc,
  COUNT_IF(element_role = 'description' AND csv_table = 'medications' AND csv_match = 'Y') AS medication_matched,
  COUNT_IF(element_role = 'description' AND csv_table = 'allergies' AND csv_match = 'Y') AS allergy_matched
FROM __DATABASE__.__SCHEMA__.__TABLE__;

SELECT
  document_id,
  element_id,
  section_loinc,
  code,
  rejected_codes,
  quote_safe,
  csv_encounter,
  row_start
FROM __DATABASE__.__SCHEMA__.__TABLE__
WHERE document_id = '37549f60-b5a3-69cd-dea6-5a71c4bc23cf'
  AND element_id IN ('medications-desc-2', 'medications-code-2', 'allergies-desc-1', 'allergies-code-1')
ORDER BY element_id;
