-- Schemas, grants, and the GOV contract layer. Runs as CONCORDIA_ADMIN.
-- Rerunnable. Append-only tables (EVIDENCE, QUERY_AUDIT, PIPELINE_RUN) are CREATE IF NOT EXISTS.

USE ROLE CONCORDIA_ADMIN;
USE WAREHOUSE CONCORDIA_WH;
USE DATABASE CONCORDIA;

CREATE SCHEMA IF NOT EXISTS SIM COMMENT = 'Test-only: hidden simulation truth and defect catalog. No product grants.';
CREATE SCHEMA IF NOT EXISTS LAND COMMENT = 'Stages, raw VARIANT records, quarantine.';
CREATE SCHEMA IF NOT EXISTS CORE COMMENT = 'Canonical entities, event ledger, knowledge graph, metric contribution functions.';
CREATE SCHEMA IF NOT EXISTS GOV COMMENT = 'Contracts, ontology, mappings, entitlements, evidence, audit.';
CREATE SCHEMA IF NOT EXISTS APP COMMENT = 'Secure views, semantic view, procedures, Streamlit.';

GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_INGEST;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_TRANSFORM;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_APP;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_AUDITOR;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_TEST;
GRANT USAGE ON SCHEMA LAND TO ROLE CONCORDIA_INGEST;
GRANT USAGE ON SCHEMA LAND TO ROLE CONCORDIA_TRANSFORM;
GRANT USAGE ON SCHEMA CORE TO ROLE CONCORDIA_TRANSFORM;
GRANT USAGE ON SCHEMA GOV TO ROLE CONCORDIA_TRANSFORM;
GRANT USAGE ON SCHEMA GOV TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON SCHEMA GOV TO ROLE CONCORDIA_AUDITOR;
GRANT USAGE ON SCHEMA APP TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON SCHEMA APP TO ROLE CONCORDIA_APP;
GRANT USAGE ON SCHEMA APP TO ROLE CONCORDIA_AUDITOR;
GRANT CREATE STREAMLIT ON SCHEMA APP TO ROLE CONCORDIA_APP_OWNER;
GRANT CREATE PROCEDURE ON SCHEMA APP TO ROLE CONCORDIA_APP_OWNER;
GRANT CREATE STAGE ON SCHEMA APP TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON SCHEMA SIM TO ROLE CONCORDIA_TEST;
GRANT USAGE ON SCHEMA CORE TO ROLE CONCORDIA_TEST;
GRANT USAGE ON SCHEMA GOV TO ROLE CONCORDIA_TEST;
GRANT USAGE ON SCHEMA APP TO ROLE CONCORDIA_TEST;

-- ---------------------------------------------------------------- metric contract
CREATE OR REPLACE TABLE GOV.METRIC_CONTRACT (
  METRIC_ID VARCHAR NOT NULL,
  METRIC_VERSION VARCHAR NOT NULL,
  DISPLAY_NAME VARCHAR NOT NULL,
  QUESTION VARCHAR NOT NULL,
  GRAIN VARCHAR NOT NULL,
  UNIT VARCHAR NOT NULL,
  PERIOD_CLOCK VARCHAR NOT NULL,
  NUMERATOR_DEF VARCHAR NOT NULL,
  DENOMINATOR_DEF VARCHAR NOT NULL,
  INCLUSIONS ARRAY,
  EXCLUSIONS ARRAY,
  SOURCE_FIELDS ARRAY,
  OWNER VARCHAR NOT NULL,
  APPROVER VARCHAR NOT NULL,
  STATUS VARCHAR NOT NULL,
  CONTRIBUTION_FUNCTION VARCHAR NOT NULL,
  RESULT_FUNCTION VARCHAR NOT NULL,
  DEFINITION_HASH VARCHAR,
  PUBLISHED_AT TIMESTAMP_TZ,
  PRIMARY KEY (METRIC_ID, METRIC_VERSION)
);

INSERT INTO GOV.METRIC_CONTRACT
SELECT column1, '1.0.0', column2, column3, column4, column5, column6, column7, column8,
       PARSE_JSON(column9), PARSE_JSON(column10), PARSE_JSON(column11), column12, column13, 'PUBLISHED', column14, column15,
       NULL, '2026-10-02T00:00:00Z'::TIMESTAMP_TZ
FROM VALUES
('INBOUND_SUPPLIER_OTD', 'Inbound supplier OTD',
 'Did the supplier complete the accepted quantity for each PO schedule line by the supplier commitment date?',
 'purchase_order_schedule_line', 'ratio of lines',
 'Supplier commitment date at the receiving facility: the acknowledged promise when visible within two governed business days of PO issue, otherwise the buyer-requested date.',
 'Eligible lines whose cumulative accepted quantity reached the ordered quantity on or before the commitment date.',
 'Eligible lines whose commitment date falls in the period.',
 '["Supplier-caused late cancellation counts as a miss","Past-due incomplete lines count as misses","Plant-caused post-acceptance holds do not fail the supplier"]',
 '["Buyer cancellation before commitment","Future open lines","Unresolved supplier, item, UOM, timezone or calendar","Missing quality disposition"]',
 '["ERP.PO_LINE","ERP.PO_ACK","ERP.PO_CANCEL","WMS.RECEIPT","MES.DISPOSITION"]',
 'Procurement', 'Data governance council', 'CORE.M1_LINES', 'CORE.COUNT_RESULT_M1'),
('OUTBOUND_CUSTOMER_OTD', 'Outbound customer OTD',
 'Did the customer receive the complete committed quantity by the original accepted promise date?',
 'sales_order_line', 'ratio of lines',
 'Original accepted customer promise date, in the timezone of the contractual completion location.',
 'Eligible lines whose governed completion (ready-for-pickup for EXW/FCA, proof of delivery for DAP/DDP) reached the required quantity on or before the original promise.',
 'Eligible lines whose original promise date falls in the period.',
 '["Failed and misdirected attempts do not count","Partial deliveries count only when the required quantity completes","Customer-approved short close before promise changes required quantity"]',
 '["Missing or unsupported Incoterm, timezone or calendar (INCOMPLETE/ABSTAIN)","Customer cancellation before pick","Pre-promise customer hold covering the deadline","Unresolved identity or UOM","Future open lines"]',
 '["ERP.SO_LINE","ERP.SO_PROMISE","ERP.SO_CHANGE","TMS.DELIVERY_EVENT","CRM.CUSTOMER_HOLD"]',
 'Logistics', 'Data governance council', 'CORE.M2_LINES', 'CORE.COUNT_RESULT_M2'),
('UNIT_FILL_RATE', 'Unit fill rate',
 'What proportion of ordered units was ship-confirmed, independent of timeliness?',
 'sales_order_line', 'ratio of units',
 'Original requested ship date in the shipping facility timezone.',
 'Sum of ship-confirmed base-UOM quantity, capped at ordered quantity per line.',
 'Sum of ordered base-UOM quantity.',
 '["Company cancellation is unfilled","Over-shipment is capped","Silent substitutes do not count"]',
 '["Customer cancellation before pick","Unresolved UOM"]',
 '["ERP.SO_LINE","ERP.SO_CHANGE","WMS.SHIP_CONFIRM"]',
 'Logistics', 'Data governance council', 'CORE.M3_LINES', 'CORE.FILL_RESULT_M3'),
('DAYS_INVENTORY', 'Days inventory',
 'For how many days would currently available inventory cover recent demand?',
 'facility_item_as_of', 'days',
 'As-of date in each facility timezone; demand is the trailing 28 complete days before it.',
 'Available quantity (WMS on hand minus quality hold minus allocated) times 28.',
 'Trailing 28-day demand: ship-confirmed quantity for finished goods, production issues for components.',
 '["Network rollup sums available quantity and demand before division"]',
 '["In-transit stock","ERP book inventory (diagnostic only)","Missing inventory class or facility scope (CLARIFY)"]',
 '["WMS.SNAPSHOT","WMS.SHIP_CONFIRM","MES.MATERIAL_ISSUE"]',
 'Supply planning', 'Data governance council', 'CORE.M4_RESULT', 'CORE.M4_RESULT'),
('LANDED_COST_PER_ACCEPTED_UNIT', 'Landed cost per accepted unit',
 'What known acquisition and inbound logistics cost was incurred for each accepted unit?',
 'accepted_receipt', 'USD per unit',
 'Local acceptance date at the receiving facility.',
 'Known allocated merchandise, freight, duty, insurance, brokerage and accessorials, less visible credits, in USD cents.',
 'Accepted quantity of covered receipts.',
 '["Freight by chargeable weight, then volume, then merchandise value across the pool","Duty and brokerage by customs value","FX at each component economic date, half-even to cents"]',
 '["Any uncovered accepted quantity makes the answer INCOMPLETE and withholds the value","Unknown duty is never zero","Rejected quantity cost is not spread"]',
 '["ERP.AP_DOC","TMS.FREIGHT_INVOICE","ERP.FX_RATE","WMS.RECEIPT","MES.DISPOSITION"]',
 'Procurement finance', 'Data governance council', 'CORE.M5_RECEIPTS', 'CORE.LANDED_RESULT_M5');

UPDATE GOV.METRIC_CONTRACT SET DEFINITION_HASH = SHA2(METRIC_ID || '|' || METRIC_VERSION || '|' || GRAIN || '|' || PERIOD_CLOCK || '|' || NUMERATOR_DEF || '|' || DENOMINATOR_DEF, 256);

CREATE OR REPLACE TABLE GOV.REJECTED_ALIAS (PHRASE VARCHAR, RESPONSE VARCHAR, OPTIONS ARRAY, NOTE VARCHAR);
INSERT INTO GOV.REJECTED_ALIAS SELECT column1, column2, PARSE_JSON(column3), column4 FROM VALUES
 ('otd', 'CLARIFY', '["INBOUND_SUPPLIER_OTD","OUTBOUND_CUSTOMER_OTD","SHOW_BOTH_UNCOMBINED"]', 'Bare OTD must clarify inbound versus outbound.'),
 ('shipping on time', 'REJECT', '["OUTBOUND_CUSTOMER_OTD"]', 'Ship date is not customer delivery.'),
 ('otif', 'REJECT', '[]', 'OTIF is not equivalent to either OTD metric.'),
 ('fill rate', 'CLARIFY', '["UNIT_FILL_RATE"]', 'Maps to unit fill rate only after explicit confirmation.'),
 ('inventory days', 'CLARIFY', '["DAYS_INVENTORY"]', 'Clarify inventory class and facility or network scope.'),
 ('cost', 'CLARIFY', '["LANDED_COST_PER_ACCEPTED_UNIT"]', 'Insufficient: ask which cost.'),
 ('merchandise plus outbound freight', 'REJECT', '[]', 'Not landed cost.'),
 ('customer rating', 'REJECT', '[]', 'Ratings are not delivery performance.');

CREATE OR REPLACE TABLE GOV.ONTOLOGY_TERM (TERM VARCHAR, KIND VARCHAR, DEFINITION VARCHAR);
INSERT INTO GOV.ONTOLOGY_TERM SELECT * FROM VALUES
 ('Party', 'ENTITY', 'Organization participating as manufacturer, supplier, customer, ship-to, carrier, broker, or internal legal entity. Key PARTY_ID.'),
 ('Part', 'ENTITY', 'Purchased component, subassembly, or finished product. Key ITEM_ID; source SKUs and GTINs are aliases.'),
 ('Facility', 'ENTITY', 'Plant or distribution centre with timezone, calendar and country. Key FACILITY_ID.'),
 ('BOM revision', 'ENTITY', 'Effective-dated parent/component structure with quantity and revision.'),
 ('Event', 'ENTITY', 'Append-only operational occurrence: receipt, disposition, issue, production, shipment, delivery attempt, delivery, invoice, correction.'),
 ('SUPPLIES', 'RELATIONSHIP', 'Supplier supplies Part.'),
 ('COMPONENT_OF', 'RELATIONSHIP', 'Part is a component of a BOM revision of a parent part.'),
 ('SUBSTITUTES_FOR', 'RELATIONSHIP', 'Part substitutes for Part under an effective approved policy.'),
 ('CAPABLE_OF_PRODUCING', 'RELATIONSHIP', 'Plant can produce Product.'),
 ('RECEIVED_FROM', 'RELATIONSHIP', 'Receipt received from Supplier.'),
 ('HELD_AT', 'RELATIONSHIP', 'Stock held at Facility.'),
 ('CONSUMES', 'RELATIONSHIP', 'Production order consumes a component.'),
 ('PRODUCES', 'RELATIONSHIP', 'Production order produces a product.'),
 ('EXECUTED_AT', 'RELATIONSHIP', 'Production order executed at Plant.'),
 ('FULFILLS', 'RELATIONSHIP', 'Shipment fulfills a sales-order line.'),
 ('PLACED', 'RELATIONSHIP', 'Customer placed a sales-order line.'),
 ('DELIVERED_TO', 'RELATIONSHIP', 'Shipment delivered to customer ship-to.'),
 ('RETURNED_AGAINST', 'RELATIONSHIP', 'Return recorded against a sales-order line.'),
 ('PROMISES', 'RELATIONSHIP', 'Promise revision promises a sales-order line.'),
 ('COST_OF', 'RELATIONSHIP', 'Cost component is a cost of a receipt.'),
 ('FEEDBACK_ON', 'RELATIONSHIP', 'Rating or complaint is feedback on a sales-order line.'),
 ('SAME_AS', 'RELATIONSHIP', 'Source identifier is the same as a canonical entity, only through an administered mapping.');

-- ---------------------------------------------------------------- master data (MDM contract)
CREATE OR REPLACE TABLE GOV.ITEM (ITEM_ID VARCHAR PRIMARY KEY, NAME VARCHAR, ITEM_TYPE VARCHAR, FAMILY VARCHAR, INVENTORY_CLASS VARCHAR, HOME_FACILITY_ID VARCHAR, UNIT_WEIGHT_KG NUMBER(18,3));
CREATE OR REPLACE TABLE GOV.PARTY (PARTY_ID VARCHAR PRIMARY KEY, PARTY_TYPE VARCHAR, NAME VARCHAR, COUNTRY VARCHAR, CURRENCY VARCHAR, PARENT_PARTY_ID VARCHAR, GEOGRAPHY_ID VARCHAR);
CREATE OR REPLACE TABLE GOV.SHIP_TO (SHIP_TO_ID VARCHAR PRIMARY KEY, CUSTOMER_ID VARCHAR, GEOGRAPHY_ID VARCHAR, TIMEZONE VARCHAR, CALENDAR_ID VARCHAR, COUNTRY VARCHAR);
CREATE OR REPLACE TABLE GOV.FACILITY (FACILITY_ID VARCHAR PRIMARY KEY, NAME VARCHAR, KIND VARCHAR, COUNTRY VARCHAR, TIMEZONE VARCHAR, CALENDAR_ID VARCHAR);
CREATE OR REPLACE TABLE GOV.GEOGRAPHY (GEOGRAPHY_ID VARCHAR PRIMARY KEY, NAME VARCHAR, COUNTRY VARCHAR, TIMEZONE VARCHAR);
CREATE OR REPLACE TABLE GOV.CALENDAR (CALENDAR_ID VARCHAR PRIMARY KEY, NAME VARCHAR, SHUTDOWNS ARRAY);
CREATE OR REPLACE TABLE GOV.CALENDAR_DAY (CALENDAR_ID VARCHAR, DAY DATE, IS_BUSINESS BOOLEAN, BUSINESS_ORDINAL NUMBER);
CREATE OR REPLACE TABLE GOV.LANE (LANE_ID VARCHAR PRIMARY KEY, ORIGIN_ID VARCHAR, DESTINATION_ID VARCHAR, MODE VARCHAR, TRANSIT_MU NUMBER(9,2), CARRIER VARCHAR);
CREATE OR REPLACE TABLE GOV.SUPPLY (SUPPLIER_ID VARCHAR, ITEM_ID VARCHAR);
CREATE OR REPLACE TABLE GOV.UOM_CONVERSION (ITEM_ID VARCHAR, FROM_UOM VARCHAR, TO_UOM VARCHAR, FACTOR NUMBER(18,6));
CREATE OR REPLACE TABLE GOV.SUBSTITUTION (ITEM_ID VARCHAR, SUBSTITUTE_ITEM_ID VARCHAR, VALID_FROM DATE, VALID_TO DATE, APPROVED_BY VARCHAR);
CREATE OR REPLACE TABLE GOV.SOURCE_ALIAS (SOURCE_SYSTEM VARCHAR, ENTITY_TYPE VARCHAR, SOURCE_KEY VARCHAR, CANONICAL_ID VARCHAR, METHOD VARCHAR, VALID_FROM DATE DEFAULT TO_DATE('2025-01-01'));

CREATE OR REPLACE TABLE GOV.SOURCE_MAPPING (
  SOURCE_SYSTEM VARCHAR, SOURCE_OBJECT VARCHAR, SOURCE_FIELD VARCHAR, CANONICAL_TARGET VARCHAR,
  TRANSFORM_RULE VARCHAR, DATATYPE VARCHAR, POLICY VARCHAR, REQUIRED BOOLEAN, OWNER VARCHAR, VALID_FROM DATE DEFAULT TO_DATE('2025-01-01')
);
INSERT INTO GOV.SOURCE_MAPPING (SOURCE_SYSTEM, SOURCE_OBJECT, SOURCE_FIELD, CANONICAL_TARGET, TRANSFORM_RULE, DATATYPE, POLICY, REQUIRED, OWNER) SELECT * FROM VALUES
 ('ERP','PO_LINE','vendor_no','CORE.PO_LINE.SUPPLIER_ID','GOV.SOURCE_ALIAS ERP/SUPPLIER','VARCHAR','unmapped -> IDENTITY_UNRESOLVED',TRUE,'Procurement'),
 ('ERP','PO_LINE','material_no','CORE.PO_LINE.ITEM_ID','GOV.SOURCE_ALIAS ERP/ITEM','VARCHAR','unmapped -> IDENTITY_UNRESOLVED',TRUE,'Procurement'),
 ('ERP','PO_LINE','plant_code','CORE.PO_LINE.FACILITY_ID','GOV.SOURCE_ALIAS ERP/FACILITY','VARCHAR','facility timezone and calendar from GOV.FACILITY',TRUE,'Procurement'),
 ('ERP','PO_LINE','qty+uom','CORE.PO_LINE.ORDERED_QTY','GOV.UOM_CONVERSION to EA','NUMBER(38,6)','no conversion -> UOM_UNRESOLVED',TRUE,'Procurement'),
 ('ERP','PO_LINE','issued','CORE.PO_LINE.ISSUED_ON','YYYY-MM-DD | MM/DD/YYYY | DD.MM.YYYY','DATE','unparseable -> quarantine',TRUE,'Procurement'),
 ('ERP','PO_ACK','ack_date+promised_date','CORE.PO_LINE.ACK_*','first acknowledgement revision','DATE','visible_at governs usability',FALSE,'Procurement'),
 ('WMS','RECEIPT','qty+uom','CORE.RECEIPT','GTIN and GLN aliases, UOM conversion','NUMBER(38,6)','CASE=12 EA',TRUE,'Warehouse'),
 ('MES','DISPOSITION','kind+qty+local_ts','CORE.PO_ACCEPTANCE','ACCEPT and RELEASE are acceptances; local plant clock','NUMBER(38,6)','missing -> DISPOSITION_MISSING',TRUE,'Quality'),
 ('ERP','SO_LINE','customer_no+ship_to_no','CORE.SO_LINE.CUSTOMER_ID/SHIP_TO_ID','GOV.SOURCE_ALIAS','VARCHAR','unmapped -> IDENTITY_UNRESOLVED',TRUE,'Sales'),
 ('ERP','SO_LINE','incoterm','CORE.SO_LINE.INCOTERM','EXW, FCA, DAP, DDP only','VARCHAR','missing/unsupported -> excluded, INCOMPLETE',TRUE,'Sales'),
 ('ERP','SO_PROMISE','promise_date','CORE.SO_LINE.ORIGINAL_PROMISE_ON / CORE.PROMISE_REVISION','first ORIGINAL revision is the contract; later revisions diagnostic','DATE','append-only',TRUE,'Sales'),
 ('CRM','PROMISE_CURRENT','promise_date','(diagnostic only)','overwritten in CRM; never the contract','DATE','conflict reported',FALSE,'Sales'),
 ('TMS','DELIVERY_EVENT','local_ts+tz','CORE.SO_DELIVERY_EVENT','local business date at event location','DATE','missing tz -> quarantine, TIMEZONE_MISSING on line',TRUE,'Logistics'),
 ('WMS','SHIP_CONFIRM','gtin+qty','CORE.SO_SHIPMENT','GTIN alias; mismatch without SUBSTITUTION -> SILENT','NUMBER(38,6)','',TRUE,'Warehouse'),
 ('WMS','SNAPSHOT','on_hand,hold,allocated,in_transit','CORE.INVENTORY_SNAPSHOT','GTIN and GLN aliases','NUMBER(38,6)','',TRUE,'Warehouse'),
 ('MES','MATERIAL_ISSUE','qty+issued_local','CORE.DEMAND_EVENT','component demand at plant local date','NUMBER(38,6)','',TRUE,'Production'),
 ('ERP','AP_DOC','amount+currency+dates','CORE.COST_COMPONENT','first revision = obligation, first revision with amount = amount','NUMBER(38,0) cents','amount null -> not visible',TRUE,'Finance'),
 ('TMS','FREIGHT_INVOICE','amount+members','CORE.COST_COMPONENT (FREIGHT)','one pool per invoice','NUMBER(38,0) cents','weight -> volume -> merchandise basis',TRUE,'Finance'),
 ('ERP','FX_RATE','usd_per_unit','CORE.COST_COMPONENT.FX_RATE','rate at component economic date','NUMBER(38,12)','missing -> FX_MISSING',TRUE,'Treasury'),
 ('IOT','DOCK_SENSOR','event_ts+sensor_id+truck_id','CORE.IOT_EVENT','event time is UTC; GTIN and GLN use administered aliases','TIMESTAMP_TZ','unmapped item/site -> unresolved',TRUE,'Logistics'),
 ('IOT','DOCK_SENSOR','lot_id+receipt_ref+shipment_ref','CORE.LOT_TRACE','lot links dock telemetry to a receipt or shipment','VARCHAR','append-only synthetic genealogy',TRUE,'Warehouse');

-- ---------------------------------------------------------------- entitlements, verified questions
CREATE OR REPLACE TABLE GOV.ENTITLEMENT (
  PERSONA VARCHAR PRIMARY KEY, DISPLAY_NAME VARCHAR, TITLE VARCHAR, ALLOWED_FACILITIES ARRAY, COST_VISIBLE BOOLEAN, AUDIT_VISIBLE BOOLEAN,
  VALID_FROM DATE, VALID_TO DATE
);
INSERT INTO GOV.ENTITLEMENT SELECT column1, column2, column3, PARSE_JSON(column4), column5, column6, '2025-01-01'::DATE, NULL FROM VALUES
 ('EXECUTIVE', 'Nora Hale', 'VP Supply Chain', '["*"]', TRUE, FALSE),
 ('PLANNER', 'Priya Shah', 'Supply Planner', '["*"]', FALSE, FALSE),
 ('PROCUREMENT', 'Marcus Webb', 'Procurement Manager', '["*"]', TRUE, FALSE),
 ('LOGISTICS', 'Elena Voss', 'Logistics Manager', '["*"]', FALSE, FALSE),
 ('AUDITOR', 'Jordan Ellis', 'Data Steward / Auditor', '["*"]', TRUE, TRUE);

CREATE OR REPLACE TABLE GOV.VERIFIED_QUESTION (
  QUESTION_ID VARCHAR PRIMARY KEY, QUESTION VARCHAR, METRIC_ID VARCHAR, SCOPE OBJECT, PERIOD_START DATE, PERIOD_END DATE,
  AS_OF_KIND VARCHAR, COMPARE_TO VARCHAR, BENCHMARK_CLASS VARCHAR
);
INSERT INTO GOV.VERIFIED_QUESTION SELECT column1, column2, column3, PARSE_JSON(column4)::OBJECT, column5::DATE, column6::DATE, column7, column8, column9 FROM VALUES
 ('VQ-01','Why did outbound customer OTD for MM-440 change in May 2026?','OUTBOUND_CUSTOMER_OTD','{"item_id":"MM-440","geography_id":"GEO-NORTHEAST"}','2026-05-01','2026-05-31','final','PRIOR_PERIOD','change'),
 ('VQ-02','Inbound supplier OTD for MM-440 at Dayton in May 2026','INBOUND_SUPPLIER_OTD','{"item_id":"MM-440","facility_id":"FAC-DAYTON"}','2026-05-01','2026-05-31','final',NULL,'value'),
 ('VQ-03','Outbound customer OTD for MM-440 in the Northeast in May 2026','OUTBOUND_CUSTOMER_OTD','{"item_id":"MM-440","geography_id":"GEO-NORTHEAST"}','2026-05-01','2026-05-31','final',NULL,'value'),
 ('VQ-04','Unit fill rate for MM-440 in May 2026','UNIT_FILL_RATE','{"item_id":"MM-440"}','2026-05-01','2026-05-31','final',NULL,'value'),
 ('VQ-05','Days inventory of MM-440 finished goods at Dayton','DAYS_INVENTORY','{"item_id":"MM-440","facility_id":"FAC-DAYTON","inventory_class":"FINISHED_GOODS"}','2026-07-01','2026-07-31','final',NULL,'value'),
 ('VQ-06','Landed cost per accepted unit for MM-440 at Dayton in May 2026','LANDED_COST_PER_ACCEPTED_UNIT','{"item_id":"MM-440","facility_id":"FAC-DAYTON"}','2026-05-01','2026-05-31','final',NULL,'value'),
 ('VQ-07','Landed cost for MM-440 at Dayton in May 2026 as known on 5 June','LANDED_COST_PER_ACCEPTED_UNIT','{"item_id":"MM-440","facility_id":"FAC-DAYTON"}','2026-05-01','2026-05-31','early',NULL,'as_of'),
 ('VQ-08','Compare landed cost for MM-440 at Dayton in May 2026 between 5 June and 15 July','LANDED_COST_PER_ACCEPTED_UNIT','{"item_id":"MM-440","facility_id":"FAC-DAYTON"}','2026-05-01','2026-05-31','final','EARLY_AS_OF','as_of_replay'),
 ('VQ-09','Outbound customer OTD by region for May 2026','OUTBOUND_CUSTOMER_OTD','{}','2026-05-01','2026-05-31','final',NULL,'breakdown'),
 ('VQ-10','Inbound supplier OTD trend for Dayton','INBOUND_SUPPLIER_OTD','{"facility_id":"FAC-DAYTON"}','2025-01-01','2026-06-30','final',NULL,'trend'),
 ('VQ-11','Network days inventory for MM-440 finished goods','DAYS_INVENTORY','{"item_id":"MM-440","inventory_class":"FINISHED_GOODS","network":true}','2026-07-01','2026-07-31','final',NULL,'value'),
 ('VQ-12','Unit fill rate by region for May 2026','UNIT_FILL_RATE','{}','2026-05-01','2026-05-31','final',NULL,'breakdown');

-- ---------------------------------------------------------------- evidence and audit (append-only)
CREATE TABLE IF NOT EXISTS GOV.EVIDENCE (
  EVIDENCE_ID VARCHAR NOT NULL, CREATED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(), PERSONA VARCHAR, QUESTION VARCHAR,
  METRIC_ID VARCHAR, METRIC_VERSION VARCHAR, DEFINITION_HASH VARCHAR, SCOPE VARIANT, PERIOD_START DATE, PERIOD_END DATE, AS_OF TIMESTAMP_TZ,
  STATUS VARCHAR, ENVELOPE VARIANT, EVIDENCE_HASH VARCHAR, QUERY_ID VARCHAR, ORIGIN VARCHAR
);
CREATE TABLE IF NOT EXISTS GOV.QUERY_AUDIT (
  AUDIT_ID VARCHAR, CREATED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(), SNOWFLAKE_USER VARCHAR, SNOWFLAKE_ROLE VARCHAR, PERSONA VARCHAR,
  QUESTION VARCHAR, NORMALIZED VARCHAR, ROUTE VARCHAR, CLARIFICATION VARCHAR, SEMANTIC_OBJECT VARCHAR, SQL_HASH VARCHAR, QUERY_ID VARCHAR,
  EVIDENCE_ID VARCHAR, MODEL VARCHAR, STATUS VARCHAR, DETAIL VARIANT
);
CREATE TABLE IF NOT EXISTS GOV.PIPELINE_RUN (
  RUN_ID VARCHAR, STARTED_AT TIMESTAMP_TZ, FINISHED_AT TIMESTAMP_TZ, STEP VARCHAR, STATUS VARCHAR, ROWS_IN NUMBER, ROWS_OUT NUMBER, DETAIL VARIANT
);
CREATE OR REPLACE TABLE GOV.QUALITY_RESULT (CHECKED_AT TIMESTAMP_TZ, CHECK_NAME VARCHAR, OBJECT_NAME VARCHAR, RESULT NUMBER, THRESHOLD NUMBER, PASSED BOOLEAN, DETAIL VARCHAR);
CREATE OR REPLACE TABLE GOV.MODEL_PIN (PURPOSE VARCHAR, MODEL VARCHAR, PINNED_AT TIMESTAMP_TZ, NOTE VARCHAR);
INSERT INTO GOV.MODEL_PIN SELECT * FROM VALUES
 ('NARRATION', '__NARRATION_MODEL__', '2026-10-02T00:00:00Z'::TIMESTAMP_TZ, 'AI_COMPLETE narrates a stored envelope only; numeric tokens are checked against the envelope.'),
 ('ANALYST', 'cortex-analyst', '2026-10-02T00:00:00Z'::TIMESTAMP_TZ, 'Semantic view APP.SUPPLY_CHAIN_ONTOLOGY; generated SQL is allowlisted before execution.');

GRANT SELECT ON ALL TABLES IN SCHEMA GOV TO ROLE CONCORDIA_TRANSFORM;
GRANT SELECT ON TABLE GOV.METRIC_CONTRACT TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.REJECTED_ALIAS TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.ONTOLOGY_TERM TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.ENTITLEMENT TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.VERIFIED_QUESTION TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.MODEL_PIN TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.SOURCE_MAPPING TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT, INSERT ON TABLE GOV.EVIDENCE TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT, INSERT ON TABLE GOV.QUERY_AUDIT TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.PIPELINE_RUN TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.QUALITY_RESULT TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON ALL TABLES IN SCHEMA GOV TO ROLE CONCORDIA_AUDITOR;
GRANT SELECT ON ALL TABLES IN SCHEMA GOV TO ROLE CONCORDIA_TEST;
GRANT INSERT ON TABLE GOV.PIPELINE_RUN TO ROLE CONCORDIA_TRANSFORM;
GRANT INSERT ON TABLE GOV.QUALITY_RESULT TO ROLE CONCORDIA_TRANSFORM;
