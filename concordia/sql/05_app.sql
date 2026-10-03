-- APP layer: published metric grid, secure views, governed ask, narration.
-- Aggregate templates are substituted by scripts/deploy.py from scripts/metric_sql.py, so the published grid
-- and the CORE.*_RESULT functions aggregate with identical SQL text.

USE ROLE CONCORDIA_ADMIN;
USE WAREHOUSE CONCORDIA_WH;
USE DATABASE CONCORDIA;

UPDATE GOV.METRIC_CONTRACT SET RESULT_FUNCTION = CASE METRIC_ID
    WHEN 'INBOUND_SUPPLIER_OTD' THEN 'CORE.COUNT_RESULT_M1' WHEN 'OUTBOUND_CUSTOMER_OTD' THEN 'CORE.COUNT_RESULT_M2'
    WHEN 'UNIT_FILL_RATE' THEN 'CORE.FILL_RESULT_M3' WHEN 'DAYS_INVENTORY' THEN 'CORE.M4_RESULT' ELSE 'CORE.LANDED_RESULT_M5' END,
  CONTRIBUTION_FUNCTION = IFF(METRIC_ID = 'DAYS_INVENTORY', 'CORE.M4_RESULT', CONTRIBUTION_FUNCTION),
  DEFINITION_HASH = SHA2(CONCAT_WS('|', METRIC_ID, METRIC_VERSION, GRAIN, UNIT, PERIOD_CLOCK, NUMERATOR_DEF, DENOMINATOR_DEF,
                                   TO_JSON(INCLUSIONS), TO_JSON(EXCLUSIONS)));

-- ---------------------------------------------------------------- published tables
CREATE TABLE IF NOT EXISTS APP.PUBLISH_RUN (
  RUN_ID VARCHAR, STARTED_AT TIMESTAMP_TZ, FINISHED_AT TIMESTAMP_TZ, RAW_RECORDS NUMBER, RESULT_ROWS NUMBER, NOTE VARCHAR
);
CREATE TABLE IF NOT EXISTS APP.METRIC_RESULT (
  RUN_ID VARCHAR, WORLD_ID VARCHAR, METRIC_ID VARCHAR, METRIC_VERSION VARCHAR, AS_OF_KIND VARCHAR, AS_OF TIMESTAMP_TZ,
  PERIOD_START DATE, PERIOD_END DATE, ITEM_ID VARCHAR, FACILITY_ID VARCHAR, GEOGRAPHY_ID VARCHAR, SUPPLIER_ID VARCHAR, CUSTOMER_ID VARCHAR,
  INVENTORY_CLASS VARCHAR, NETWORK BOOLEAN,
  STATUS VARCHAR, NUMERATOR VARCHAR, DENOMINATOR VARCHAR, DISPLAY VARCHAR, VALUE_NUM NUMBER(38,12), REASONS ARRAY, COVERAGE VARCHAR,
  DIAGNOSTIC_DISPLAY VARCHAR, EXCLUDED_COUNT NUMBER, AFFECTED_COMMITMENTS NUMBER, AFFECTED_UNITS VARCHAR, UNRESOLVED_RECORDS NUMBER,
  EVIDENCE_IDS ARRAY, ORIGIN VARCHAR, PUBLISHED_AT TIMESTAMP_TZ
);
CREATE TABLE IF NOT EXISTS APP.METRIC_CONTRIBUTION (
  RUN_ID VARCHAR, METRIC_ID VARCHAR, AS_OF_KIND VARCHAR, AS_OF TIMESTAMP_TZ, LINE_ID VARCHAR, PERIOD_DATE DATE, ITEM_ID VARCHAR,
  FACILITY_ID VARCHAR, SUPPLIER_ID VARCHAR, GEOGRAPHY_ID VARCHAR, CUSTOMER_ID VARCHAR, OUTCOME VARCHAR, REASONS ARRAY,
  QTY NUMBER(38,6), FILLED_QTY NUMBER(38,6), COMMITMENT_ON DATE, COMPLETED_ON DATE, DRIVER VARCHAR
);
CREATE TABLE IF NOT EXISTS APP.RECEIPT_CONTRIBUTION (
  RUN_ID VARCHAR, AS_OF_KIND VARCHAR, AS_OF TIMESTAMP_TZ, RECEIPT_ID VARCHAR, PERIOD_DATE DATE, ITEM_ID VARCHAR, FACILITY_ID VARCHAR,
  SUPPLIER_ID VARCHAR, ACCEPTED_QTY NUMBER(38,6), GAPS ARRAY, COVERED BOOLEAN, CENTS NUMBER(38,0), FREIGHT_SHARE NUMBER(38,0)
);
CREATE TRANSIENT TABLE IF NOT EXISTS APP.ASK_SCRATCH (
  EVIDENCE_ID VARCHAR, STATUS VARCHAR, NUMERATOR VARCHAR, DENOMINATOR VARCHAR, DISPLAY VARCHAR, VALUE_NUM NUMBER(38,12), REASONS ARRAY,
  COVERAGE VARCHAR, DIAGNOSTIC_DISPLAY VARCHAR, EXCLUDED_COUNT NUMBER, AFFECTED_COMMITMENTS NUMBER, AFFECTED_UNITS VARCHAR,
  UNRESOLVED_RECORDS NUMBER, EVIDENCE_IDS ARRAY
);

-- ---------------------------------------------------------------- publisher
CREATE OR REPLACE PROCEDURE APP.PUBLISH_RESULTS()
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
  run_id VARCHAR DEFAULT UUID_STRING();
  started TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_TZ;
  final_at TIMESTAMP_TZ DEFAULT '2026-07-15T23:59:59Z'::TIMESTAMP_TZ;
  grid CURSOR FOR
    WITH m AS (SELECT DATEADD(month, SEQ4(), '2025-01-01'::DATE) AS PS FROM TABLE(GENERATOR(ROWCOUNT => 18)))
    SELECT 'early' AS KIND, TO_TIMESTAMP_TZ(TO_VARCHAR(DATEADD(day, 4, DATEADD(month, 1, PS))) || 'T23:59:59Z') AS A, PS, LAST_DAY(PS) AS PE FROM m
    UNION ALL SELECT 'final', '2026-07-15T23:59:59Z'::TIMESTAMP_TZ, '2025-01-01'::DATE, '2026-06-30'::DATE
    ORDER BY A;
  m4 CURSOR FOR
    WITH m AS (SELECT DATEADD(month, SEQ4(), '2025-01-01'::DATE) AS PS FROM TABLE(GENERATOR(ROWCOUNT => 18)))
    SELECT 'early' AS KIND, TO_TIMESTAMP_TZ(TO_VARCHAR(DATEADD(day, 4, DATEADD(month, 1, PS))) || 'T23:59:59Z') AS A, PS, LAST_DAY(PS) AS PE FROM m
    UNION ALL SELECT 'final', '2026-07-15T23:59:59Z'::TIMESTAMP_TZ, '2026-07-01'::DATE, '2026-07-31'::DATE;
  raw_rows NUMBER;
  result_rows NUMBER;
BEGIN
  DELETE FROM APP.METRIC_CONTRIBUTION;
  DELETE FROM APP.RECEIPT_CONTRIBUTION;
  FOR g IN grid DO
    LET k VARCHAR := g.KIND;
    LET a TIMESTAMP_TZ := g.A;
    LET ps DATE := g.PS;
    LET pe DATE := g.PE;
    INSERT INTO APP.METRIC_CONTRIBUTION
      SELECT :run_id, 'INBOUND_SUPPLIER_OTD', :k, :a, LINE_ID, PERIOD_DATE, ITEM_ID, FACILITY_ID, SUPPLIER_ID, GEOGRAPHY_ID, CUSTOMER_ID,
             OUTCOME, REASONS, QTY, FILLED_QTY, COMMITMENT_ON, COMPLETED_ON, DRIVER
      FROM TABLE(CORE.M1_LINES('MERIDIAN', :a)) WHERE PERIOD_DATE BETWEEN :ps AND :pe;
    INSERT INTO APP.METRIC_CONTRIBUTION
      SELECT :run_id, 'OUTBOUND_CUSTOMER_OTD', :k, :a, LINE_ID, PERIOD_DATE, ITEM_ID, FACILITY_ID, SUPPLIER_ID, GEOGRAPHY_ID, CUSTOMER_ID,
             OUTCOME, REASONS, QTY, FILLED_QTY, COMMITMENT_ON, COMPLETED_ON, DRIVER
      FROM TABLE(CORE.M2_LINES('MERIDIAN', :a)) WHERE PERIOD_DATE BETWEEN :ps AND :pe;
    INSERT INTO APP.METRIC_CONTRIBUTION
      SELECT :run_id, 'UNIT_FILL_RATE', :k, :a, LINE_ID, PERIOD_DATE, ITEM_ID, FACILITY_ID, SUPPLIER_ID, GEOGRAPHY_ID, CUSTOMER_ID,
             OUTCOME, REASONS, QTY, FILLED_QTY, COMMITMENT_ON, COMPLETED_ON, DRIVER
      FROM TABLE(CORE.M3_LINES('MERIDIAN', :a)) WHERE PERIOD_DATE BETWEEN :ps AND :pe;
    INSERT INTO APP.RECEIPT_CONTRIBUTION
      SELECT :run_id, :k, :a, RECEIPT_ID, PERIOD_DATE, ITEM_ID, FACILITY_ID, SUPPLIER_ID, ACCEPTED_QTY, GAPS, COVERED, CENTS, FREIGHT_SHARE
      FROM TABLE(CORE.M5_RECEIPTS('MERIDIAN', :a)) WHERE PERIOD_DATE BETWEEN :ps AND :pe;
  END FOR;

  INSERT INTO APP.METRIC_RESULT
    SELECT :run_id, 'MERIDIAN', METRIC_ID, '1.0.0', AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), LAST_DAY(DATE_TRUNC('month', PERIOD_DATE)),
           ITEM_ID, FACILITY_ID, GEOGRAPHY_ID, SUPPLIER_ID, CUSTOMER_ID, NULL, NULL,
           {{COUNT_AGG}},
           'DERIVED_FROM_SYNTHETIC', CURRENT_TIMESTAMP()::TIMESTAMP_TZ
    FROM APP.METRIC_CONTRIBUTION WHERE METRIC_ID IN ('INBOUND_SUPPLIER_OTD', 'OUTBOUND_CUSTOMER_OTD')
    GROUP BY GROUPING SETS (
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE)),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), FACILITY_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), GEOGRAPHY_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), SUPPLIER_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), CUSTOMER_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID, FACILITY_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID, GEOGRAPHY_ID))
    HAVING (GROUPING(ITEM_ID) = 1 OR ITEM_ID IS NOT NULL) AND (GROUPING(FACILITY_ID) = 1 OR FACILITY_ID IS NOT NULL)
       AND (GROUPING(GEOGRAPHY_ID) = 1 OR GEOGRAPHY_ID IS NOT NULL) AND (GROUPING(SUPPLIER_ID) = 1 OR SUPPLIER_ID IS NOT NULL)
       AND (GROUPING(CUSTOMER_ID) = 1 OR CUSTOMER_ID IS NOT NULL);

  INSERT INTO APP.METRIC_RESULT
    SELECT :run_id, 'MERIDIAN', METRIC_ID, '1.0.0', AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), LAST_DAY(DATE_TRUNC('month', PERIOD_DATE)),
           ITEM_ID, FACILITY_ID, GEOGRAPHY_ID, NULL, CUSTOMER_ID, NULL, NULL,
           {{FILL_AGG}},
           'DERIVED_FROM_SYNTHETIC', CURRENT_TIMESTAMP()::TIMESTAMP_TZ
    FROM APP.METRIC_CONTRIBUTION WHERE METRIC_ID = 'UNIT_FILL_RATE'
    GROUP BY GROUPING SETS (
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE)),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), FACILITY_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), GEOGRAPHY_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), CUSTOMER_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID, FACILITY_ID),
      (METRIC_ID, AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID, GEOGRAPHY_ID))
    HAVING (GROUPING(ITEM_ID) = 1 OR ITEM_ID IS NOT NULL) AND (GROUPING(FACILITY_ID) = 1 OR FACILITY_ID IS NOT NULL)
       AND (GROUPING(GEOGRAPHY_ID) = 1 OR GEOGRAPHY_ID IS NOT NULL) AND (GROUPING(CUSTOMER_ID) = 1 OR CUSTOMER_ID IS NOT NULL);

  INSERT INTO APP.METRIC_RESULT
    SELECT :run_id, 'MERIDIAN', 'LANDED_COST_PER_ACCEPTED_UNIT', '1.0.0', AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE),
           LAST_DAY(DATE_TRUNC('month', PERIOD_DATE)), ITEM_ID, FACILITY_ID, NULL, SUPPLIER_ID, NULL, NULL, NULL,
           {{LANDED_AGG}},
           'DERIVED_FROM_SYNTHETIC', CURRENT_TIMESTAMP()::TIMESTAMP_TZ
    FROM APP.RECEIPT_CONTRIBUTION
    GROUP BY GROUPING SETS (
      (AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE)),
      (AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID),
      (AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), FACILITY_ID),
      (AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), SUPPLIER_ID),
      (AS_OF_KIND, AS_OF, DATE_TRUNC('month', PERIOD_DATE), ITEM_ID, FACILITY_ID))
    HAVING (GROUPING(ITEM_ID) = 1 OR ITEM_ID IS NOT NULL) AND (GROUPING(FACILITY_ID) = 1 OR FACILITY_ID IS NOT NULL)
       AND (GROUPING(SUPPLIER_ID) = 1 OR SUPPLIER_ID IS NOT NULL);

  -- One set-based function call publishes every observed finished part at its site scopes and network scope.
  FOR g IN m4 DO
    LET k VARCHAR := g.KIND;
    LET a TIMESTAMP_TZ := g.A;
    LET ps DATE := g.PS;
    LET pe DATE := g.PE;
    INSERT INTO APP.METRIC_RESULT
      SELECT :run_id, 'MERIDIAN', 'DAYS_INVENTORY', '1.0.0', :k, :a, :ps, :pe,
             r.ITEM_ID, r.FACILITY_ID, NULL, NULL, NULL, 'FINISHED_GOODS', r.NETWORK,
             r.* EXCLUDE (ITEM_ID, FACILITY_ID, NETWORK), 'DERIVED_FROM_SYNTHETIC', CURRENT_TIMESTAMP()::TIMESTAMP_TZ
      FROM TABLE(CORE.M4_GRID('MERIDIAN', :a, 'FINISHED_GOODS')) r;
  END FOR;

  SELECT COUNT(*) INTO :raw_rows FROM LAND.RAW_RECORD;
  SELECT COUNT(*) INTO :result_rows FROM APP.METRIC_RESULT WHERE RUN_ID = :run_id;
  INSERT INTO APP.PUBLISH_RUN SELECT :run_id, :started, CURRENT_TIMESTAMP()::TIMESTAMP_TZ, :raw_rows, :result_rows, NULL;
  INSERT INTO GOV.PIPELINE_RUN SELECT :run_id, :started, CURRENT_TIMESTAMP()::TIMESTAMP_TZ, 'APP.PUBLISH_RESULTS', 'SUCCEEDED', :raw_rows, :result_rows,
    OBJECT_CONSTRUCT('result_rows', :result_rows);
  RETURN OBJECT_CONSTRUCT('run_id', :run_id, 'result_rows', :result_rows, 'raw_records', :raw_rows);
END;
$$;

-- ---------------------------------------------------------------- secure views for the app
CREATE OR REPLACE SECURE VIEW APP.V_PUBLISH_RUN AS
  SELECT RUN_ID, STARTED_AT, FINISHED_AT, RAW_RECORDS, RESULT_ROWS,
         ROW_NUMBER() OVER (ORDER BY FINISHED_AT DESC) AS RECENCY
  FROM APP.PUBLISH_RUN;

CREATE OR REPLACE SECURE VIEW APP.V_RESULT AS
  SELECT r.*, p.RECENCY
  FROM APP.METRIC_RESULT r JOIN APP.V_PUBLISH_RUN p ON p.RUN_ID = r.RUN_ID
  WHERE r.WORLD_ID = 'MERIDIAN' AND p.RECENCY <= 2;

CREATE OR REPLACE SECURE VIEW APP.V_RESULT_CURRENT AS
  SELECT * EXCLUDE (RECENCY) FROM APP.V_RESULT WHERE RECENCY = 1;

CREATE OR REPLACE SECURE VIEW APP.V_RESTATEMENT AS
  SELECT c.METRIC_ID, c.AS_OF_KIND, c.PERIOD_START, c.ITEM_ID, c.FACILITY_ID, c.GEOGRAPHY_ID, c.SUPPLIER_ID, c.CUSTOMER_ID,
         p.STATUS AS PRIOR_STATUS, p.DISPLAY AS PRIOR_DISPLAY, p.COVERAGE AS PRIOR_COVERAGE, p.REASONS AS PRIOR_REASONS, p.RUN_ID AS PRIOR_RUN_ID,
         c.STATUS, c.DISPLAY, c.COVERAGE, c.REASONS, c.RUN_ID
  FROM APP.V_RESULT c
  JOIN APP.V_RESULT p
    ON p.RECENCY = 2 AND c.RECENCY = 1 AND p.METRIC_ID = c.METRIC_ID AND p.AS_OF_KIND = c.AS_OF_KIND AND p.PERIOD_START = c.PERIOD_START
   AND EQUAL_NULL(p.ITEM_ID, c.ITEM_ID) AND EQUAL_NULL(p.FACILITY_ID, c.FACILITY_ID) AND EQUAL_NULL(p.GEOGRAPHY_ID, c.GEOGRAPHY_ID)
   AND EQUAL_NULL(p.SUPPLIER_ID, c.SUPPLIER_ID) AND EQUAL_NULL(p.CUSTOMER_ID, c.CUSTOMER_ID) AND EQUAL_NULL(p.NETWORK, c.NETWORK)
  WHERE NOT EQUAL_NULL(p.STATUS, c.STATUS) OR NOT EQUAL_NULL(p.DISPLAY, c.DISPLAY) OR NOT EQUAL_NULL(p.COVERAGE, c.COVERAGE);

CREATE OR REPLACE SECURE VIEW APP.V_CONTRIBUTION AS
  SELECT METRIC_ID, AS_OF_KIND, AS_OF, LINE_ID, PERIOD_DATE, DATE_TRUNC('month', PERIOD_DATE) AS PERIOD_START, ITEM_ID, FACILITY_ID,
         SUPPLIER_ID, GEOGRAPHY_ID, CUSTOMER_ID, OUTCOME, REASONS, QTY, FILLED_QTY, COMMITMENT_ON, COMPLETED_ON, DRIVER
  FROM APP.METRIC_CONTRIBUTION;

CREATE OR REPLACE SECURE VIEW APP.V_RECEIPT_CONTRIBUTION AS
  SELECT AS_OF_KIND, AS_OF, RECEIPT_ID, PERIOD_DATE, DATE_TRUNC('month', PERIOD_DATE) AS PERIOD_START, ITEM_ID, FACILITY_ID, SUPPLIER_ID,
         ACCEPTED_QTY, GAPS, COVERED, TO_VARCHAR(ROUND(CENTS / 100, 2)::NUMBER(38,2)) AS LANDED_USD, TO_VARCHAR(ROUND(FREIGHT_SHARE / 100, 2)::NUMBER(38,2)) AS FREIGHT_USD
  FROM APP.RECEIPT_CONTRIBUTION;

CREATE OR REPLACE SECURE VIEW APP.V_BRIDGE AS
  SELECT METRIC_ID, AS_OF_KIND, DATE_TRUNC('month', PERIOD_DATE) AS PERIOD_START, ITEM_ID, FACILITY_ID, GEOGRAPHY_ID, SUPPLIER_ID, CUSTOMER_ID,
         COALESCE(DRIVER, OUTCOME) AS DRIVER, COUNT(*) AS LINES, TO_VARCHAR(SUM(QTY)::NUMBER(38,6)) AS UNITS
  FROM APP.METRIC_CONTRIBUTION
  WHERE OUTCOME IN ('MISS', 'EXCLUDED')
  GROUP BY ALL;

CREATE OR REPLACE SECURE VIEW APP.V_ITEM AS SELECT ITEM_ID, NAME, ITEM_TYPE, FAMILY, INVENTORY_CLASS, HOME_FACILITY_ID FROM GOV.ITEM;
CREATE OR REPLACE SECURE VIEW APP.V_FACILITY AS SELECT FACILITY_ID, NAME, KIND, COUNTRY, TIMEZONE, CALENDAR_ID FROM GOV.FACILITY;
CREATE OR REPLACE SECURE VIEW APP.V_PARTY AS SELECT PARTY_ID, PARTY_TYPE, NAME, COUNTRY, GEOGRAPHY_ID FROM GOV.PARTY;
CREATE OR REPLACE SECURE VIEW APP.V_GEOGRAPHY AS SELECT GEOGRAPHY_ID, NAME, COUNTRY FROM GOV.GEOGRAPHY;
CREATE OR REPLACE SECURE VIEW APP.V_CONTRACT AS
  SELECT METRIC_ID, METRIC_VERSION, DISPLAY_NAME, QUESTION, GRAIN, UNIT, PERIOD_CLOCK, NUMERATOR_DEF, DENOMINATOR_DEF, INCLUSIONS, EXCLUSIONS,
         SOURCE_FIELDS, OWNER, APPROVER, STATUS, RESULT_FUNCTION, DEFINITION_HASH, PUBLISHED_AT
  FROM GOV.METRIC_CONTRACT;
CREATE OR REPLACE SECURE VIEW APP.V_VERIFIED_QUESTION AS SELECT * FROM GOV.VERIFIED_QUESTION;
CREATE OR REPLACE SECURE VIEW APP.V_ENTITLEMENT AS SELECT PERSONA, DISPLAY_NAME, TITLE, COST_VISIBLE, AUDIT_VISIBLE FROM GOV.ENTITLEMENT;
CREATE OR REPLACE SECURE VIEW APP.V_REJECTED_ALIAS AS SELECT * FROM GOV.REJECTED_ALIAS;
CREATE OR REPLACE SECURE VIEW APP.V_ONTOLOGY AS SELECT * FROM GOV.ONTOLOGY_TERM;
CREATE OR REPLACE SECURE VIEW APP.V_SOURCE_MAPPING AS
  SELECT SOURCE_SYSTEM, SOURCE_OBJECT, SOURCE_FIELD, CANONICAL_TARGET, TRANSFORM_RULE, POLICY, OWNER FROM GOV.SOURCE_MAPPING;

CREATE OR REPLACE SECURE VIEW APP.V_KG_NODE AS SELECT NODE_ID, NODE_TYPE, LABEL, PROPS, ORIGIN FROM CORE.KG_NODE;
CREATE OR REPLACE SECURE VIEW APP.V_KG_EDGE AS
  SELECT EDGE_TYPE, SRC_ID, DST_ID, VALID_FROM, VALID_TO, EVIDENCE_ID, ORIGIN, RESOLUTION_METHOD FROM CORE.KG_EDGE;

CREATE OR REPLACE SECURE VIEW APP.V_SOURCE_COUNTS AS
  SELECT SOURCE_SYSTEM, SOURCE_OBJECT, COUNT(*) AS RECORDS, COUNT(DISTINCT SOURCE_RECORD_ID) AS DISTINCT_RECORDS,
         MAX(EXTRACTED_AT) AS LAST_EXTRACTED_AT, MAX(LOADED_AT) AS LAST_LOADED_AT, ANY_VALUE(ORIGIN) AS ORIGIN
  FROM LAND.RAW_RECORD GROUP BY ALL;
CREATE OR REPLACE SECURE VIEW APP.V_QUARANTINE AS
  SELECT SOURCE_SYSTEM, SOURCE_OBJECT, SOURCE_RECORD_ID, REASON, DETAIL, VISIBLE_AT FROM LAND.QUARANTINE;
CREATE OR REPLACE SECURE VIEW APP.V_RESOLUTION AS
  SELECT SOURCE_SYSTEM, ENTITY_TYPE, SOURCE_KEY, CANDIDATE_ID, METHOD, SCORE, STATUS FROM CORE.RESOLUTION_CANDIDATE;
CREATE OR REPLACE SECURE VIEW APP.V_ALIAS AS
  SELECT SOURCE_SYSTEM, ENTITY_TYPE, SOURCE_KEY, CANONICAL_ID, METHOD FROM GOV.SOURCE_ALIAS;
CREATE OR REPLACE SECURE VIEW APP.V_PIPELINE AS
  SELECT RUN_ID, STARTED_AT, FINISHED_AT, STEP, STATUS, ROWS_IN, ROWS_OUT, DETAIL FROM GOV.PIPELINE_RUN;
CREATE OR REPLACE SECURE VIEW APP.V_EVIDENCE AS
  SELECT EVIDENCE_ID, CREATED_AT, PERSONA, QUESTION, METRIC_ID, METRIC_VERSION, DEFINITION_HASH, SCOPE, PERIOD_START, PERIOD_END, AS_OF,
         STATUS, ENVELOPE, EVIDENCE_HASH, ORIGIN
  FROM GOV.EVIDENCE;
CREATE OR REPLACE SECURE VIEW APP.V_QUERY_AUDIT AS
  SELECT AUDIT_ID, CREATED_AT, SNOWFLAKE_USER, PERSONA, QUESTION, ROUTE, CLARIFICATION, SEMANTIC_OBJECT, EVIDENCE_ID, MODEL, STATUS, DETAIL
  FROM GOV.QUERY_AUDIT;
CREATE OR REPLACE SECURE VIEW APP.V_LEDGER AS
  SELECT EVENT_ID, EVENT_TYPE, ACTION, BIZ_STEP, DISPOSITION, EVENT_TIME, RECORD_TIME, READ_POINT, ITEM_ID, QTY, UOM, BIZ_TRANSACTION,
         SOURCE_SYSTEM, SOURCE_RECORD_ID, ORIGIN
  FROM CORE.EVENT_LEDGER;

CREATE OR REPLACE SECURE VIEW APP.V_PROMISE_CONFLICT AS
  SELECT LINE_ID, ERP_LATEST_PROMISE, CRM_PROMISE, ORIGINAL_PROMISE, DETECTED_AT FROM CORE.PROMISE_CONFLICT WHERE WORLD_ID = 'MERIDIAN';

-- ---------------------------------------------------------------- persona-masked reads for the app
CREATE OR REPLACE SECURE FUNCTION APP.RESULTS_FOR(P_PERSONA VARCHAR, P_ITEM VARCHAR, P_FACILITY VARCHAR, P_GEO VARCHAR,
                                                  P_SUPPLIER VARCHAR, P_CUSTOMER VARCHAR)
RETURNS TABLE (METRIC_ID VARCHAR, AS_OF_KIND VARCHAR, AS_OF TIMESTAMP_TZ, PERIOD_START DATE, PERIOD_END DATE, NETWORK BOOLEAN, RECENCY NUMBER,
               RUN_ID VARCHAR, STATUS VARCHAR, NUMERATOR VARCHAR, DENOMINATOR VARCHAR, DISPLAY VARCHAR, VALUE_NUM NUMBER(38,12),
               PERCENT_DISPLAY VARCHAR, REASONS ARRAY, COVERAGE VARCHAR, DIAGNOSTIC_DISPLAY VARCHAR, EXCLUDED_COUNT NUMBER,
               AFFECTED_COMMITMENTS NUMBER, AFFECTED_UNITS VARCHAR, UNRESOLVED_RECORDS NUMBER, EVIDENCE_COUNT NUMBER, MASKED BOOLEAN)
AS
$$
WITH e AS (SELECT * FROM GOV.ENTITLEMENT WHERE PERSONA = P_PERSONA), r AS (
  SELECT r.*, (e.PERSONA IS NULL OR (r.METRIC_ID = 'LANDED_COST_PER_ACCEPTED_UNIT' AND NOT COALESCE(e.COST_VISIBLE, FALSE))) AS M
  FROM APP.V_RESULT r LEFT JOIN e ON TRUE
  WHERE EQUAL_NULL(r.ITEM_ID, P_ITEM) AND EQUAL_NULL(r.FACILITY_ID, P_FACILITY) AND EQUAL_NULL(r.GEOGRAPHY_ID, P_GEO)
    AND EQUAL_NULL(r.SUPPLIER_ID, P_SUPPLIER) AND EQUAL_NULL(r.CUSTOMER_ID, P_CUSTOMER)
)
SELECT METRIC_ID, AS_OF_KIND, AS_OF, PERIOD_START, PERIOD_END, NETWORK, RECENCY, RUN_ID,
       IFF(M, 'FORBIDDEN', STATUS), IFF(M, NULL, NUMERATOR), IFF(M, NULL, DENOMINATOR), IFF(M, NULL, DISPLAY), IFF(M, NULL, VALUE_NUM),
       IFF(M OR VALUE_NUM IS NULL OR METRIC_ID NOT IN ('INBOUND_SUPPLIER_OTD', 'OUTBOUND_CUSTOMER_OTD', 'UNIT_FILL_RATE'), NULL,
           TO_VARCHAR(ROUND(VALUE_NUM * 100, 1, 'HALF_TO_EVEN')::NUMBER(38,1))),
       IFF(M, ARRAY_CONSTRUCT('COST_NOT_ENTITLED'), REASONS), IFF(M, NULL, COVERAGE), IFF(M, NULL, DIAGNOSTIC_DISPLAY),
       EXCLUDED_COUNT, AFFECTED_COMMITMENTS, AFFECTED_UNITS, UNRESOLVED_RECORDS, ARRAY_SIZE(EVIDENCE_IDS), M
FROM r
$$;

CREATE OR REPLACE SECURE FUNCTION APP.BREAKDOWN_FOR(P_PERSONA VARCHAR, P_METRIC VARCHAR, P_PERIOD DATE, P_ASOF_KIND VARCHAR, P_DIM VARCHAR,
                                                    P_ITEM VARCHAR)
RETURNS TABLE (DIM_VALUE VARCHAR, STATUS VARCHAR, NUMERATOR VARCHAR, DENOMINATOR VARCHAR, DISPLAY VARCHAR, VALUE_NUM NUMBER(38,12),
               PERCENT_DISPLAY VARCHAR, COVERAGE VARCHAR, AFFECTED_COMMITMENTS NUMBER, AFFECTED_UNITS VARCHAR, EXCLUDED_COUNT NUMBER, MASKED BOOLEAN)
AS
$$
WITH e AS (SELECT * FROM GOV.ENTITLEMENT WHERE PERSONA = P_PERSONA), r AS (
  SELECT r.*, (e.PERSONA IS NULL OR (r.METRIC_ID = 'LANDED_COST_PER_ACCEPTED_UNIT' AND NOT COALESCE(e.COST_VISIBLE, FALSE))) AS M,
         CASE P_DIM WHEN 'FACILITY' THEN r.FACILITY_ID WHEN 'GEOGRAPHY' THEN r.GEOGRAPHY_ID WHEN 'SUPPLIER' THEN r.SUPPLIER_ID
                    WHEN 'CUSTOMER' THEN r.CUSTOMER_ID WHEN 'ITEM' THEN r.ITEM_ID END AS D
  FROM APP.V_RESULT r LEFT JOIN e ON TRUE
  WHERE r.RECENCY = 1 AND r.METRIC_ID = P_METRIC AND r.PERIOD_START = P_PERIOD AND r.AS_OF_KIND = P_ASOF_KIND
    AND (P_DIM = 'ITEM' OR EQUAL_NULL(r.ITEM_ID, P_ITEM))
    AND (P_DIM = 'FACILITY' OR r.FACILITY_ID IS NULL) AND (P_DIM = 'GEOGRAPHY' OR r.GEOGRAPHY_ID IS NULL)
    AND (P_DIM = 'SUPPLIER' OR r.SUPPLIER_ID IS NULL) AND (P_DIM = 'CUSTOMER' OR r.CUSTOMER_ID IS NULL)
    AND r.METRIC_ID <> 'DAYS_INVENTORY'
)
SELECT D, IFF(M, 'FORBIDDEN', STATUS), IFF(M, NULL, NUMERATOR), IFF(M, NULL, DENOMINATOR), IFF(M, NULL, DISPLAY), IFF(M, NULL, VALUE_NUM),
       IFF(M OR VALUE_NUM IS NULL OR METRIC_ID NOT IN ('INBOUND_SUPPLIER_OTD', 'OUTBOUND_CUSTOMER_OTD', 'UNIT_FILL_RATE'), NULL,
           TO_VARCHAR(ROUND(VALUE_NUM * 100, 1, 'HALF_TO_EVEN')::NUMBER(38,1))),
       IFF(M, NULL, COVERAGE), AFFECTED_COMMITMENTS, AFFECTED_UNITS, EXCLUDED_COUNT, M
FROM r WHERE D IS NOT NULL
$$;

CREATE OR REPLACE SECURE FUNCTION APP.RECEIPTS_FOR(P_PERSONA VARCHAR, P_PERIOD DATE, P_ASOF_KIND VARCHAR, P_ITEM VARCHAR, P_FACILITY VARCHAR)
RETURNS TABLE (RECEIPT_ID VARCHAR, PERIOD_DATE DATE, ITEM_ID VARCHAR, FACILITY_ID VARCHAR, SUPPLIER_ID VARCHAR, ACCEPTED_QTY NUMBER(38,6),
               GAPS ARRAY, COVERED BOOLEAN, LANDED_USD VARCHAR, FREIGHT_USD VARCHAR, MASKED BOOLEAN)
AS
$$
WITH e AS (SELECT * FROM GOV.ENTITLEMENT WHERE PERSONA = P_PERSONA)
SELECT r.RECEIPT_ID, r.PERIOD_DATE, r.ITEM_ID, r.FACILITY_ID, r.SUPPLIER_ID, r.ACCEPTED_QTY, r.GAPS, r.COVERED,
       IFF(COALESCE(e.COST_VISIBLE, FALSE), r.LANDED_USD, NULL), IFF(COALESCE(e.COST_VISIBLE, FALSE), r.FREIGHT_USD, NULL),
       NOT COALESCE(e.COST_VISIBLE, FALSE)
FROM APP.V_RECEIPT_CONTRIBUTION r LEFT JOIN e ON TRUE
WHERE r.PERIOD_START = P_PERIOD AND r.AS_OF_KIND = P_ASOF_KIND
  AND (P_ITEM IS NULL OR r.ITEM_ID = P_ITEM) AND (P_FACILITY IS NULL OR r.FACILITY_ID = P_FACILITY)
$$;

CREATE OR REPLACE SECURE FUNCTION APP.EVIDENCE_FOR(P_PERSONA VARCHAR)
RETURNS TABLE (EVIDENCE_ID VARCHAR, CREATED_AT TIMESTAMP_TZ, PERSONA VARCHAR, QUESTION VARCHAR, METRIC_ID VARCHAR, STATUS VARCHAR,
               AS_OF TIMESTAMP_TZ, DEFINITION_HASH VARCHAR, EVIDENCE_HASH VARCHAR, ENVELOPE VARIANT)
AS
$$
SELECT v.EVIDENCE_ID, v.CREATED_AT, v.PERSONA, v.QUESTION, v.METRIC_ID, v.STATUS, v.AS_OF, v.DEFINITION_HASH, v.EVIDENCE_HASH, v.ENVELOPE
FROM GOV.EVIDENCE v JOIN GOV.ENTITLEMENT e ON e.PERSONA = P_PERSONA
WHERE e.AUDIT_VISIBLE OR v.PERSONA = P_PERSONA
$$;

CREATE OR REPLACE SECURE FUNCTION APP.AUDIT_FOR(P_PERSONA VARCHAR)
RETURNS TABLE (AUDIT_ID VARCHAR, CREATED_AT TIMESTAMP_TZ, SNOWFLAKE_USER VARCHAR, PERSONA VARCHAR, QUESTION VARCHAR, ROUTE VARCHAR,
               CLARIFICATION VARCHAR, EVIDENCE_ID VARCHAR, MODEL VARCHAR, STATUS VARCHAR)
AS
$$
SELECT a.AUDIT_ID, a.CREATED_AT, a.SNOWFLAKE_USER, a.PERSONA, a.QUESTION, a.ROUTE, a.CLARIFICATION, a.EVIDENCE_ID, a.MODEL, a.STATUS
FROM GOV.QUERY_AUDIT a JOIN GOV.ENTITLEMENT e ON e.PERSONA = P_PERSONA
WHERE e.AUDIT_VISIBLE OR a.PERSONA = P_PERSONA
$$;

-- ---------------------------------------------------------------- governed answer: one metric, one scope, one as-of
CREATE OR REPLACE PROCEDURE APP.ASK_METRIC(P_PERSONA VARCHAR, P_QUESTION VARCHAR, P_METRIC VARCHAR, P_SCOPE VARIANT,
                                           P_PS DATE, P_PE DATE, P_ASOF_KIND VARCHAR, P_ROUTE VARCHAR)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
  ev VARCHAR DEFAULT UUID_STRING();
  known NUMBER;
  cost_ok BOOLEAN;
  asof TIMESTAMP_TZ;
  item VARCHAR;
  fac VARCHAR;
  geo VARCHAR;
  sup VARCHAR;
  cust VARCHAR;
  klass VARCHAR;
  net BOOLEAN;
  env VARIANT;
  defhash VARCHAR;
  dname VARCHAR;
  status VARCHAR;
  report_ps DATE DEFAULT P_PS;
  report_pe DATE DEFAULT P_PE;
BEGIN
  SELECT COUNT(*), COALESCE(BOOLOR_AGG(COST_VISIBLE), FALSE) INTO :known, :cost_ok FROM GOV.ENTITLEMENT WHERE PERSONA = :P_PERSONA;
  SELECT MAX(DEFINITION_HASH), MAX(DISPLAY_NAME) INTO :defhash, :dname FROM GOV.METRIC_CONTRACT WHERE METRIC_ID = :P_METRIC;
  asof := IFF(LOWER(:P_ASOF_KIND) = 'early',
              TO_TIMESTAMP_TZ(TO_VARCHAR(DATEADD(day, 4, DATEADD(month, 1, DATE_TRUNC('month', :P_PE)))) || 'T23:59:59Z'),
              '2026-07-15T23:59:59Z'::TIMESTAMP_TZ);
  item := P_SCOPE:item_id::VARCHAR;
  fac := P_SCOPE:facility_id::VARCHAR;
  geo := P_SCOPE:geography_id::VARCHAR;
  sup := P_SCOPE:supplier_id::VARCHAR;
  cust := P_SCOPE:customer_id::VARCHAR;
  klass := P_SCOPE:inventory_class::VARCHAR;
  net := COALESCE(P_SCOPE:network::BOOLEAN, FALSE);
  IF (P_METRIC = 'DAYS_INVENTORY' AND LOWER(P_ASOF_KIND) = 'final') THEN
    report_ps := '2026-07-01'::DATE;
    report_pe := '2026-07-31'::DATE;
  END IF;

  IF (known = 0) THEN
    INSERT INTO APP.ASK_SCRATCH (EVIDENCE_ID, STATUS, REASONS, EVIDENCE_IDS, EXCLUDED_COUNT, AFFECTED_COMMITMENTS, UNRESOLVED_RECORDS)
      SELECT :ev, 'FORBIDDEN', ARRAY_CONSTRUCT('PERSONA_UNKNOWN'), ARRAY_CONSTRUCT(), 0, 0, 0;
  ELSEIF (P_METRIC = 'LANDED_COST_PER_ACCEPTED_UNIT' AND NOT cost_ok) THEN
    INSERT INTO APP.ASK_SCRATCH (EVIDENCE_ID, STATUS, REASONS, EVIDENCE_IDS, EXCLUDED_COUNT, AFFECTED_COMMITMENTS, UNRESOLVED_RECORDS)
      SELECT :ev, 'FORBIDDEN', ARRAY_CONSTRUCT('COST_NOT_ENTITLED'), ARRAY_CONSTRUCT(), 0, 0, 0;
  ELSEIF (P_METRIC = 'INBOUND_SUPPLIER_OTD') THEN
    INSERT INTO APP.ASK_SCRATCH SELECT :ev, * FROM TABLE(CORE.COUNT_RESULT_M1('MERIDIAN', :P_PS, :P_PE, :asof, :item, :fac, :geo, :sup, :cust));
  ELSEIF (P_METRIC = 'OUTBOUND_CUSTOMER_OTD') THEN
    INSERT INTO APP.ASK_SCRATCH SELECT :ev, * FROM TABLE(CORE.COUNT_RESULT_M2('MERIDIAN', :P_PS, :P_PE, :asof, :item, :fac, :geo, :sup, :cust));
  ELSEIF (P_METRIC = 'UNIT_FILL_RATE') THEN
    INSERT INTO APP.ASK_SCRATCH SELECT :ev, * FROM TABLE(CORE.FILL_RESULT_M3('MERIDIAN', :P_PS, :P_PE, :asof, :item, :fac, :geo, :sup, :cust));
  ELSEIF (P_METRIC = 'DAYS_INVENTORY') THEN
    INSERT INTO APP.ASK_SCRATCH SELECT :ev, * FROM TABLE(CORE.M4_RESULT('MERIDIAN', :asof, :item, :fac, :klass, :net));
  ELSEIF (P_METRIC = 'LANDED_COST_PER_ACCEPTED_UNIT') THEN
    INSERT INTO APP.ASK_SCRATCH SELECT :ev, * FROM TABLE(CORE.LANDED_RESULT_M5('MERIDIAN', :P_PS, :P_PE, :asof, :item, :fac, :sup));
  ELSE
    INSERT INTO APP.ASK_SCRATCH (EVIDENCE_ID, STATUS, REASONS, EVIDENCE_IDS, EXCLUDED_COUNT, AFFECTED_COMMITMENTS, UNRESOLVED_RECORDS)
      SELECT :ev, 'CLARIFY', ARRAY_CONSTRUCT('METRIC_UNKNOWN'), ARRAY_CONSTRUCT(), 0, 0, 0;
  END IF;

  SELECT OBJECT_CONSTRUCT_KEEP_NULL(
           'metric_id', :P_METRIC, 'metric_version', '1.0.0', 'display_name', :dname, 'definition_hash', :defhash,
           'scope', :P_SCOPE, 'period', ARRAY_CONSTRUCT(TO_VARCHAR(:report_ps), TO_VARCHAR(:report_pe)),
           'as_of', TO_VARCHAR(:asof, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'as_of_kind', LOWER(:P_ASOF_KIND),
           'status', STATUS, 'numerator', NUMERATOR, 'denominator', DENOMINATOR, 'display', DISPLAY,
           'percent', IFF(:P_METRIC IN ('INBOUND_SUPPLIER_OTD', 'OUTBOUND_CUSTOMER_OTD', 'UNIT_FILL_RATE') AND VALUE_NUM IS NOT NULL,
                          TO_VARCHAR(ROUND(VALUE_NUM * 100, 2, 'HALF_TO_EVEN')::NUMBER(38,2)), NULL),
           'reasons', COALESCE(REASONS, ARRAY_CONSTRUCT()), 'coverage', COVERAGE, 'diagnostic_display', DIAGNOSTIC_DISPLAY,
           'excluded_count', EXCLUDED_COUNT, 'affected_commitments', AFFECTED_COMMITMENTS, 'affected_units', AFFECTED_UNITS,
           'unresolved_records', UNRESOLVED_RECORDS, 'evidence_count', ARRAY_SIZE(COALESCE(EVIDENCE_IDS, ARRAY_CONSTRUCT())),
           'evidence_sample', ARRAY_SLICE(COALESCE(EVIDENCE_IDS, ARRAY_CONSTRUCT()), 0, 40),
           'origin', 'DERIVED_FROM_SYNTHETIC', 'route', :P_ROUTE, 'persona', :P_PERSONA),
         STATUS
    INTO :env, :status
  FROM APP.ASK_SCRATCH WHERE EVIDENCE_ID = :ev;
  DELETE FROM APP.ASK_SCRATCH WHERE EVIDENCE_ID = :ev;

  INSERT INTO GOV.EVIDENCE (EVIDENCE_ID, PERSONA, QUESTION, METRIC_ID, METRIC_VERSION, DEFINITION_HASH, SCOPE, PERIOD_START, PERIOD_END, AS_OF,
                            STATUS, ENVELOPE, EVIDENCE_HASH, QUERY_ID, ORIGIN)
    SELECT :ev, :P_PERSONA, :P_QUESTION, :P_METRIC, '1.0.0', :defhash, :P_SCOPE, :report_ps, :report_pe, :asof, :status, :env, SHA2(TO_JSON(:env)),
           LAST_QUERY_ID(), 'DERIVED_FROM_SYNTHETIC';
  RETURN OBJECT_INSERT(:env, 'evidence_id', :ev);
END;
$$;

-- ---------------------------------------------------------------- conversational router and narration
CREATE OR REPLACE PROCEDURE APP.ASK(P_PERSONA VARCHAR, P_QUESTION VARCHAR)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
EXECUTE AS OWNER
AS
$$
import json
import re
import uuid

METRICS = ("INBOUND_SUPPLIER_OTD", "OUTBOUND_CUSTOMER_OTD", "UNIT_FILL_RATE", "DAYS_INVENTORY", "LANDED_COST_PER_ACCEPTED_UNIT")
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                          "october", "november", "december"])}
NUMBER = re.compile(r"\d+(?:\.\d+)?")


def one(session, sql, params=None):
    rows = session.sql(sql, params=params).collect()
    return rows[0][0] if rows else None


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\- ]", " ", (text or "").lower())).strip()


def audit(session, persona, question, route, status, clarification=None, evidence_id=None, model=None, detail=None):
    session.sql(
        "INSERT INTO GOV.QUERY_AUDIT (AUDIT_ID, SNOWFLAKE_USER, SNOWFLAKE_ROLE, PERSONA, QUESTION, NORMALIZED, ROUTE, CLARIFICATION, "
        "SEMANTIC_OBJECT, EVIDENCE_ID, MODEL, STATUS, DETAIL) "
        "SELECT ?, CURRENT_USER(), CURRENT_ROLE(), ?, ?, ?, ?, ?, 'APP.ASK_METRIC', ?, ?, ?, PARSE_JSON(?)",
        params=[str(uuid.uuid4()), persona, question, norm(question), route, clarification, evidence_id, model, status,
                json.dumps(detail or {}, default=str)]).collect()


def alias_route(session, q):
    has_direction = re.search(r"\b(inbound|supplier|vendor|outbound|customer)\b", q)
    for phrase, response, options, note in session.sql("SELECT PHRASE, RESPONSE, OPTIONS, NOTE FROM GOV.REJECTED_ALIAS").collect():
        if not re.search(r"\b" + re.escape(phrase) + r"\b", q):
            continue
        if phrase == "otd" and has_direction:
            continue
        if phrase == "cost" and "landed" in q:
            continue
        if phrase == "fill rate" and "unit fill rate" in q:
            continue
        if phrase == "inventory days" and re.search(r"finished|raw|work in process|wip", q):
            continue
        return {"response": response, "phrase": phrase, "options": json.loads(options) if isinstance(options, str) else options, "note": note}
    return None


def verified_route(session, q):
    rows = session.sql(
        "SELECT QUESTION_ID, METRIC_ID, SCOPE, PERIOD_START, PERIOD_END, AS_OF_KIND, COMPARE_TO, JAROWINKLER_SIMILARITY(LOWER(QUESTION), ?) AS S "
        "FROM GOV.VERIFIED_QUESTION ORDER BY S DESC LIMIT 1", params=[q]).collect()
    if rows and rows[0]["S"] >= 92:
        r = rows[0]
        return {"question_id": r["QUESTION_ID"], "metric_id": r["METRIC_ID"], "scope": json.loads(r["SCOPE"]) if r["SCOPE"] else {},
                "period_start": str(r["PERIOD_START"]), "period_end": str(r["PERIOD_END"]), "as_of_kind": r["AS_OF_KIND"],
                "compare_to": r["COMPARE_TO"]}
    return None


def model_route(session, model, question):
    items = [r[0] for r in session.sql("SELECT ITEM_ID FROM GOV.ITEM WHERE ITEM_TYPE = 'FINISHED' ORDER BY 1").collect()]
    facilities = {r[0]: r[1] for r in session.sql("SELECT FACILITY_ID, NAME FROM GOV.FACILITY").collect()}
    geos = {r[0]: r[1] for r in session.sql("SELECT GEOGRAPHY_ID, NAME FROM GOV.GEOGRAPHY").collect()}
    prompt = (
        "You map a supply chain question to a governed metric request. Reply with JSON only, no prose.\n"
        f"metric_id must be one of {list(METRICS)} or null.\n"
        "INBOUND_SUPPLIER_OTD = supplier delivered PO lines on time. OUTBOUND_CUSTOMER_OTD = customer orders delivered on time. "
        "UNIT_FILL_RATE = units shipped versus ordered. DAYS_INVENTORY = days of supply on hand. "
        "LANDED_COST_PER_ACCEPTED_UNIT = landed cost per accepted unit.\n"
        f"facility_id one of {facilities}. geography_id one of {geos}. item_id looks like MM-401..MM-440 (finished) or CP-xxxx (components).\n"
        "inventory_class one of FINISHED_GOODS, RAW_MATERIAL, WORK_IN_PROCESS. Data covers 2025-01 to 2026-06.\n"
        'Schema: {"metric_id": str|null, "scope": {"item_id"?: str, "facility_id"?: str, "geography_id"?: str, "inventory_class"?: str, '
        '"network"?: bool}, "period_start": "YYYY-MM-DD"|null, "period_end": "YYYY-MM-DD"|null, "as_of_kind": "final"|"early", '
        '"clarify": str|null}\n'
        "If the metric or month is ambiguous, set clarify to a short question.\n"
        f"Question: {question}")
    text = one(session, "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?)", params=[model, prompt])
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return None, text
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None, text
    scope = {k: v for k, v in (parsed.get("scope") or {}).items() if v not in (None, "", False)}
    if scope.get("item_id") and scope["item_id"] not in items and not str(scope["item_id"]).startswith("CP-"):
        parsed["clarify"] = parsed.get("clarify") or f"I do not know item {scope['item_id']}."
    if scope.get("facility_id") and scope["facility_id"] not in facilities:
        parsed["clarify"] = parsed.get("clarify") or f"I do not know facility {scope['facility_id']}."
    if scope.get("geography_id") and scope["geography_id"] not in geos:
        parsed["clarify"] = parsed.get("clarify") or f"I do not know region {scope['geography_id']}."
    if parsed.get("metric_id") not in METRICS:
        parsed["metric_id"] = None
    parsed["scope"] = scope
    return parsed, text


def allowed_numbers(envelopes):
    tokens = set()
    for env in envelopes:
        tokens.update(NUMBER.findall(json.dumps(env)))
    expanded = set(tokens)
    for token in tokens:
        if "." in token:
            expanded.add(token.rstrip("0").rstrip("."))
        expanded.add(token.lstrip("0") or "0")
    return expanded


def narrate(session, model, question, envelope, compare):
    allowed = allowed_numbers([e for e in (envelope, compare) if e])
    prompt = (
        "Reply with two or three plain sentences and nothing else (no preamble, no headings) that answer the question "
        "from this evidence envelope only. Address a business reader; do not mention JSON field names. "
        "Copy numbers exactly as written in the envelope (display, percent, numerator, denominator, coverage, affected counts, dates). "
        "Do not compute new numbers. Say the data is synthetic. If status is not COMPLETE, explain why using the reasons.\n"
        f"Question: {question}\nEnvelope: {json.dumps(envelope, sort_keys=True)}\n"
        + (f"Comparison envelope: {json.dumps(compare, sort_keys=True)}\n" if compare else ""))
    try:
        text = one(session, "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?)", params=[model, prompt]) or ""
    except Exception as exc:  # noqa: BLE001
        return template(envelope, compare), "TEMPLATE", f"model error: {exc}"[:300]
    stray = sorted({t for t in NUMBER.findall(text) if t not in allowed and (t.lstrip("0") or "0") not in allowed})
    if stray:
        return template(envelope, compare), "TEMPLATE", f"rejected model numbers {stray[:6]}"
    return text.strip(), "MODEL", None


def template(env, compare):
    name = env.get("display_name") or env.get("metric_id")
    period = " to ".join(env.get("period") or [])
    if env.get("status") == "COMPLETE":
        value = env.get("percent") + "%" if env.get("percent") else env.get("display")
        text = f"{name} for {period} is {value} ({env.get('numerator')} / {env.get('denominator')}), as of {env.get('as_of')}."
    elif env.get("status") == "FORBIDDEN":
        text = f"{name} is not available to this persona ({', '.join(env.get('reasons') or [])})."
    else:
        text = (f"{name} for {period} is {env.get('status')} as of {env.get('as_of')}: "
                f"{', '.join(env.get('reasons') or []) or 'no qualifying records'}.")
    if compare:
        text += f" As of {compare.get('as_of')} it was {compare.get('status')} {compare.get('display') or ''}".rstrip() + "."
    return text + " Synthetic data."


def run(session, persona, question):
    model = one(session, "SELECT MODEL FROM GOV.MODEL_PIN WHERE PURPOSE = 'NARRATION'")
    q = norm(question)
    alias = alias_route(session, q)
    if alias and alias["response"] in ("CLARIFY", "REJECT"):
        result = {"route": "ALIAS_" + alias["response"], "clarification": alias["note"], "options": alias["options"], "phrase": alias["phrase"]}
        audit(session, persona, question, result["route"], alias["response"], alias["note"], detail=result)
        return result
    request = verified_route(session, q)
    route, raw = "VERIFIED_QUESTION", None
    if request is None:
        route = "MODEL_ROUTED"
        request, raw = model_route(session, model, question)
        if request is None or request.get("clarify") or not request.get("metric_id") or not request.get("period_start"):
            clarification = (request or {}).get("clarify") or "Which metric and month do you mean?"
            result = {"route": "CLARIFY", "clarification": clarification, "options": list(METRICS), "request": request}
            audit(session, persona, question, "CLARIFY", "CLARIFY", clarification, model=model, detail={"raw": raw})
            return result
    args = [persona, question, request["metric_id"], json.dumps(request.get("scope") or {}), request["period_start"], request["period_end"],
            request.get("as_of_kind") or "final", route]
    call = "CALL APP.ASK_METRIC(?, ?, ?, PARSE_JSON(?), ?::DATE, ?::DATE, ?, ?)"
    envelope = json.loads(one(session, call, params=args))
    compare = None
    if request.get("compare_to") == "EARLY_AS_OF":
        args[6] = "early"
        compare = json.loads(one(session, call, params=args))
    elif request.get("compare_to") == "PRIOR_PERIOD":
        start = request["period_start"]
        year, month = int(start[:4]), int(start[5:7])
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        args[4] = f"{year:04d}-{month:02d}-01"
        args[5] = one(session, "SELECT TO_VARCHAR(LAST_DAY(?::DATE))", params=[args[4]])
        compare = json.loads(one(session, call, params=args))
    narration, source, note = narrate(session, model, question, envelope, compare)
    result = {"route": route, "request": request, "envelope": envelope, "compare": compare, "narration": narration,
              "narration_source": source, "narration_note": note, "model": model}
    audit(session, persona, question, route, envelope.get("status"), evidence_id=envelope.get("evidence_id"), model=model,
          detail={"request": request, "narration_source": source, "note": note})
    return result
$$;

-- ---------------------------------------------------------------- grants
-- The app owner reads APP secure views and calls owner's-rights procedures only; no direct GOV table access.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA GOV FROM ROLE CONCORDIA_APP_OWNER;
REVOKE USAGE ON SCHEMA GOV FROM ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON ALL VIEWS IN SCHEMA APP TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON ALL VIEWS IN SCHEMA APP TO ROLE CONCORDIA_AUDITOR;
GRANT SELECT ON ALL VIEWS IN SCHEMA APP TO ROLE CONCORDIA_TEST;
GRANT USAGE ON PROCEDURE APP.ASK(VARCHAR, VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON FUNCTION APP.RESULTS_FOR(VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON FUNCTION APP.BREAKDOWN_FOR(VARCHAR, VARCHAR, DATE, VARCHAR, VARCHAR, VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON FUNCTION APP.RECEIPTS_FOR(VARCHAR, DATE, VARCHAR, VARCHAR, VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON FUNCTION APP.EVIDENCE_FOR(VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON FUNCTION APP.AUDIT_FOR(VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
-- Cost-bearing and audit views are read through the persona functions above, never directly by the app.
REVOKE SELECT ON VIEW APP.V_RESULT FROM ROLE CONCORDIA_APP_OWNER;
REVOKE SELECT ON VIEW APP.V_RESULT_CURRENT FROM ROLE CONCORDIA_APP_OWNER;
REVOKE SELECT ON VIEW APP.V_RESTATEMENT FROM ROLE CONCORDIA_APP_OWNER;
REVOKE SELECT ON VIEW APP.V_RECEIPT_CONTRIBUTION FROM ROLE CONCORDIA_APP_OWNER;
REVOKE SELECT ON VIEW APP.V_EVIDENCE FROM ROLE CONCORDIA_APP_OWNER;
REVOKE SELECT ON VIEW APP.V_QUERY_AUDIT FROM ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON PROCEDURE APP.ASK_METRIC(VARCHAR, VARCHAR, VARCHAR, VARIANT, DATE, DATE, VARCHAR, VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
