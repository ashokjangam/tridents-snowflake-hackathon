-- Supply chain ontology as a governed semantic view.
-- Entities (parts, sites, regions, suppliers, customers, metric contracts), their relationships (supplies, bill of
-- materials, capable of producing) and the governed answers published by the CORE metric functions. Each governed
-- answer is one pre-computed row, so semantic metrics select a published value and never re-aggregate ratios.

USE ROLE CONCORDIA_ADMIN;
USE WAREHOUSE CONCORDIA_WH;
USE DATABASE CONCORDIA;

DROP SEMANTIC VIEW IF EXISTS APP.CONCORDIA_METRICS;

-- ---------------------------------------------------------------- ontology views (latest publish run only)
CREATE OR REPLACE SECURE VIEW APP.SV_RESULT AS
WITH latest AS (SELECT RUN_ID FROM APP.PUBLISH_RUN QUALIFY ROW_NUMBER() OVER (ORDER BY FINISHED_AT DESC) = 1)
SELECT SHA2(CONCAT_WS('|', r.METRIC_ID, r.AS_OF_KIND, TO_VARCHAR(r.PERIOD_START), COALESCE(r.ITEM_ID, '*'), COALESCE(r.FACILITY_ID, '*'),
                      COALESCE(r.GEOGRAPHY_ID, '*'), COALESCE(r.SUPPLIER_ID, '*'), COALESCE(r.CUSTOMER_ID, '*'))) AS RESULT_KEY,
       r.METRIC_ID, r.METRIC_VERSION, r.AS_OF_KIND, r.AS_OF, r.PERIOD_START, r.PERIOD_END,
       CASE
         WHEN r.METRIC_ID = 'DAYS_INVENTORY' AND r.FACILITY_ID IS NULL THEN 'PART'
         WHEN r.METRIC_ID = 'DAYS_INVENTORY' THEN 'PART_SITE'
         WHEN COALESCE(r.ITEM_ID, r.FACILITY_ID, r.GEOGRAPHY_ID, r.SUPPLIER_ID, r.CUSTOMER_ID) IS NULL THEN 'NETWORK'
         WHEN r.ITEM_ID IS NOT NULL AND r.FACILITY_ID IS NOT NULL THEN 'PART_SITE'
         WHEN r.ITEM_ID IS NOT NULL AND r.GEOGRAPHY_ID IS NOT NULL THEN 'PART_REGION'
         WHEN r.ITEM_ID IS NOT NULL THEN 'PART'
         WHEN r.FACILITY_ID IS NOT NULL THEN 'SITE'
         WHEN r.GEOGRAPHY_ID IS NOT NULL THEN 'REGION'
         WHEN r.SUPPLIER_ID IS NOT NULL THEN 'SUPPLIER'
         ELSE 'CUSTOMER' END AS SCOPE_LEVEL,
       r.ITEM_ID, r.FACILITY_ID, r.GEOGRAPHY_ID, r.SUPPLIER_ID, r.CUSTOMER_ID,
       r.STATUS, r.NUMERATOR, r.DENOMINATOR, r.DISPLAY, r.VALUE_NUM, r.COVERAGE, ARRAY_TO_STRING(r.REASONS, ', ') AS REASONS,
       r.AFFECTED_COMMITMENTS, r.RUN_ID, r.ORIGIN
FROM APP.METRIC_RESULT r JOIN latest l ON l.RUN_ID = r.RUN_ID
WHERE r.WORLD_ID = 'MERIDIAN';

CREATE OR REPLACE SECURE VIEW APP.SV_PART AS
  SELECT ITEM_ID, NAME AS PART_NAME,
         IFF(ITEM_TYPE = 'FINISHED', 'Motor (finished good we sell)', 'Component (bought or sub-assembly)') AS PART_TYPE,
         FAMILY, HOME_FACILITY_ID
  FROM GOV.ITEM;
CREATE OR REPLACE SECURE VIEW APP.SV_SITE AS
  SELECT FACILITY_ID, NAME AS SITE_NAME, IFF(KIND = 'PLANT', 'Plant', 'Distribution centre') AS SITE_TYPE, COUNTRY FROM GOV.FACILITY;
CREATE OR REPLACE SECURE VIEW APP.SV_REGION AS SELECT GEOGRAPHY_ID, NAME AS REGION_NAME, COUNTRY FROM GOV.GEOGRAPHY;
CREATE OR REPLACE SECURE VIEW APP.SV_SUPPLIER AS
  SELECT PARTY_ID AS SUPPLIER_ID, NAME AS SUPPLIER_NAME, COUNTRY, PARENT_PARTY_ID FROM GOV.PARTY WHERE PARTY_TYPE = 'SUPPLIER';
CREATE OR REPLACE SECURE VIEW APP.SV_CUSTOMER AS
  SELECT PARTY_ID AS CUSTOMER_ID, NAME AS CUSTOMER_NAME, COUNTRY, GEOGRAPHY_ID AS CUSTOMER_REGION_ID FROM GOV.PARTY WHERE PARTY_TYPE = 'CUSTOMER';
CREATE OR REPLACE SECURE VIEW APP.SV_METRIC AS
  SELECT METRIC_ID, DISPLAY_NAME, QUESTION, UNIT, OWNER, APPROVER, METRIC_VERSION, DEFINITION_HASH, RESULT_FUNCTION FROM GOV.METRIC_CONTRACT;
CREATE OR REPLACE SECURE VIEW APP.SV_SUPPLY AS
  SELECT DISTINCT SUPPLIER_ID, ITEM_ID FROM GOV.SUPPLY;
CREATE OR REPLACE SECURE VIEW APP.SV_BOM AS
  SELECT PARENT_ID AS PARENT_ITEM_ID, COMPONENT_ID AS COMPONENT_ITEM_ID, MAX(QTY_PER) AS QTY_PER
  FROM CORE.BOM WHERE WORLD_ID = 'MERIDIAN' GROUP BY ALL;
CREATE OR REPLACE SECURE VIEW APP.SV_SOURCING AS
WITH RECURSIVE tree (MOTOR_ID, COMPONENT_ITEM_ID, BOM_LEVEL) AS (
  SELECT b.PARENT_ID, b.COMPONENT_ID, 1
  FROM CORE.BOM b JOIN GOV.ITEM i ON i.ITEM_ID = b.PARENT_ID AND i.ITEM_TYPE = 'FINISHED'
  WHERE b.WORLD_ID = 'MERIDIAN'
  UNION ALL
  SELECT t.MOTOR_ID, b.COMPONENT_ID, t.BOM_LEVEL + 1
  FROM tree t JOIN CORE.BOM b ON b.WORLD_ID = 'MERIDIAN' AND b.PARENT_ID = t.COMPONENT_ITEM_ID
  WHERE t.BOM_LEVEL < 6
)
SELECT t.MOTOR_ID, t.COMPONENT_ITEM_ID, s.SUPPLIER_ID, MIN(t.BOM_LEVEL) AS BOM_LEVEL
FROM tree t JOIN GOV.SUPPLY s ON s.ITEM_ID = t.COMPONENT_ITEM_ID
GROUP BY ALL
UNION ALL
SELECT s.ITEM_ID, s.ITEM_ID, s.SUPPLIER_ID, 0
FROM GOV.SUPPLY s JOIN GOV.ITEM i ON i.ITEM_ID = s.ITEM_ID AND i.ITEM_TYPE = 'FINISHED';
CREATE OR REPLACE SECURE VIEW APP.SV_CAPABILITY AS
  SELECT DISTINCT SPLIT_PART(SRC_ID, ':', 2) AS FACILITY_ID, SPLIT_PART(DST_ID, ':', 2) AS ITEM_ID
  FROM CORE.KG_EDGE WHERE EDGE_TYPE = 'CAPABLE_OF_PRODUCING';
CREATE OR REPLACE SECURE VIEW APP.SV_FLOW_TRACE AS
  WITH customer_routes AS (
    SELECT DISTINCT ITEM_ID AS MOTOR_ID, CUSTOMER_ID, GEOGRAPHY_ID
    FROM CORE.SO_LINE
    WHERE WORLD_ID = 'MERIDIAN' AND IDENTITY_RESOLVED
  )
  SELECT DISTINCT s.MOTOR_ID, motor.NAME AS MOTOR_NAME, s.COMPONENT_ITEM_ID, component.NAME AS COMPONENT_NAME,
         s.SUPPLIER_ID, supplier.NAME AS SUPPLIER_NAME, motor.HOME_FACILITY_ID AS FACILITY_ID,
         facility.NAME AS FACILITY_NAME, route.CUSTOMER_ID, customer.NAME AS CUSTOMER_NAME,
         route.GEOGRAPHY_ID, region.NAME AS REGION_NAME, s.BOM_LEVEL
  FROM APP.SV_SOURCING s
  JOIN GOV.ITEM motor ON motor.ITEM_ID = s.MOTOR_ID
  JOIN GOV.ITEM component ON component.ITEM_ID = s.COMPONENT_ITEM_ID
  JOIN GOV.PARTY supplier ON supplier.PARTY_ID = s.SUPPLIER_ID
  JOIN customer_routes route ON route.MOTOR_ID = s.MOTOR_ID
  JOIN GOV.FACILITY facility ON facility.FACILITY_ID = motor.HOME_FACILITY_ID
  JOIN GOV.PARTY customer ON customer.PARTY_ID = route.CUSTOMER_ID
  JOIN GOV.GEOGRAPHY region ON region.GEOGRAPHY_ID = route.GEOGRAPHY_ID;
CREATE OR REPLACE SECURE VIEW APP.SV_IOT_LOT AS
  SELECT e.EVENT_ID, e.SENSOR_ID, e.EVENT_TYPE, e.EVENT_TIME, e.TRUCK_ID, e.LOT_ID, e.ITEM_ID, item.NAME AS ITEM_NAME,
         e.FACILITY_ID, facility.NAME AS FACILITY_NAME, e.RECEIPT_ID, e.SHIPMENT_ID, e.TEMPERATURE_C
  FROM CORE.IOT_EVENT e
  LEFT JOIN GOV.ITEM item ON item.ITEM_ID = e.ITEM_ID
  LEFT JOIN GOV.FACILITY facility ON facility.FACILITY_ID = e.FACILITY_ID;
CREATE OR REPLACE SECURE VIEW APP.SV_SUBSTITUTION AS
  SELECT ITEM_ID, SUBSTITUTE_ITEM_ID, VALID_FROM, VALID_TO, APPROVED_BY FROM GOV.SUBSTITUTION;
CREATE OR REPLACE SECURE VIEW APP.SV_CONSUMPTION AS
  SELECT ISSUE_ID, ORDER_ID, COMPONENT_ID, FACILITY_ID, QTY, ISSUED_ON, LOT_ID
  FROM CORE.PRODUCTION_CONSUMPTION WHERE WORLD_ID = 'MERIDIAN';

-- Per-line outcomes stored by the same publish run as SV_RESULT: the order lines behind each governed OTD and fill-rate answer.
CREATE OR REPLACE SECURE VIEW APP.SV_LINE_OUTCOME AS
  SELECT CONCAT_WS('|', c.METRIC_ID, c.AS_OF_KIND, c.LINE_ID) AS OUTCOME_KEY, c.METRIC_ID, c.AS_OF_KIND, c.LINE_ID,
         DATE_TRUNC('month', c.PERIOD_DATE) AS PERIOD_START, c.PERIOD_DATE AS DUE_ON, c.ITEM_ID, c.FACILITY_ID, c.SUPPLIER_ID,
         c.GEOGRAPHY_ID, c.CUSTOMER_ID, c.OUTCOME, c.DRIVER AS CAUSE_CODE,
         CASE WHEN c.OUTCOME = 'HIT' THEN 'On time and complete'
              WHEN c.OUTCOME = 'EXCLUDED' THEN 'Left out: data could not be trusted'
              ELSE DECODE(c.DRIVER, 'COMPANY_CANCELLED', 'We cancelled the order', 'FAILED_OR_MISDELIVERED', 'Delivery failed or went to the wrong place',
                          'LATE_DELIVERY', 'Arrived late', 'LATE_RECEIPT', 'Supplier delivered late', 'NOT_DELIVERED', 'Not delivered yet',
                          'NOT_SHIPPED', 'Never shipped', 'OPEN_PAST_DUE', 'Still open and overdue', 'PARTIAL_DELIVERY', 'Only part of the order arrived',
                          'PARTIAL_RECEIPT', 'Supplier delivered only part', 'PARTIAL_SHIPMENT', 'Only part was shipped',
                          'PROMISE_REVISED', 'Promise date was moved; missed the original date',
                          'SILENT_SUBSTITUTE', 'A different part was shipped without approval', 'SUPPLIER_CANCELLED', 'Supplier cancelled',
                          'SUPPLIER_REJECT', 'Parts failed our quality check', 'Missed') END AS CAUSE,
         ARRAY_TO_STRING(c.REASONS, ', ') AS REASONS, c.QTY, c.FILLED_QTY, c.COMMITMENT_ON, c.COMPLETED_ON,
         IFF(c.OUTCOME = 'MISS', 1, 0) AS IS_MISS, IFF(c.OUTCOME = 'HIT', 1, 0) AS IS_HIT, IFF(c.OUTCOME = 'EXCLUDED', 1, 0) AS IS_EXCLUDED
  FROM APP.METRIC_CONTRIBUTION c
  WHERE c.RUN_ID = (SELECT RUN_ID FROM APP.PUBLISH_RUN QUALIFY ROW_NUMBER() OVER (ORDER BY FINISHED_AT DESC) = 1);

-- Operational records. Each table reaches parts, sites and parties through exactly one join path (Snowflake rejects
-- queries over a multi-path relationship), so receipts, costs and lots hang off purchase order lines, and promises,
-- shipments and allocations hang off sales order lines.
CREATE OR REPLACE SECURE VIEW APP.SV_PO_LINE AS
  SELECT LINE_ID AS PO_LINE_ID, SUPPLIER_ID, ITEM_ID, FACILITY_ID, ORDERED_QTY, ISSUED_ON, BUYER_REQUESTED_ON, ACK_PROMISE_ON,
         DATE_TRUNC('month', COALESCE(ACK_PROMISE_ON, BUYER_REQUESTED_ON)) AS DUE_MONTH, FIRST_RECEIPT_ON, INCOTERM, CANCELLATION,
         SUPPLIER_REJECTED_QTY
  FROM CORE.PO_LINE WHERE WORLD_ID = 'MERIDIAN';
CREATE OR REPLACE SECURE VIEW APP.SV_RECEIPT AS
  SELECT RECEIPT_ID, LINE_ID AS PO_LINE_ID, FACILITY_ID, RECEIVED_ON, ACCEPTED_ON, DATE_TRUNC('month', ACCEPTED_ON) AS ACCEPTED_MONTH,
         ACCEPTED_QTY, ORIGIN_COUNTRY, INCOTERM
  FROM CORE.RECEIPT WHERE WORLD_ID = 'MERIDIAN';
CREATE OR REPLACE SECURE VIEW APP.SV_RECEIPT_COST AS
  SELECT c.COMPONENT_ID AS COST_DOCUMENT_ID, c.RECEIPT_ID, r.FACILITY_ID, c.KIND AS COST_KIND, c.SOURCE_DOCUMENT_ID, c.CURRENCY,
         (c.AMOUNT_MINOR / 100)::NUMBER(38,12) AS AMOUNT, IFF(c.AMOUNT_MINOR IS NULL, 'Amount not in yet', 'Amount known') AS AMOUNT_STATE,
         c.INVOICE_DATE, c.BUYER_CHARGED, 'LANDED_COST_PER_ACCEPTED_UNIT' AS COST_METRIC
  FROM CORE.COST_COMPONENT c JOIN CORE.RECEIPT r ON r.WORLD_ID = c.WORLD_ID AND r.RECEIPT_ID = c.RECEIPT_ID
  WHERE c.WORLD_ID = 'MERIDIAN';
CREATE OR REPLACE SECURE VIEW APP.SV_RECEIPT_LOT AS
  SELECT LOT_ID, SOURCE_ID AS RECEIPT_ID, FACILITY_ID, QTY, EVENT_TIME FROM CORE.LOT_TRACE WHERE SOURCE_TYPE = 'RECEIPT';
CREATE OR REPLACE SECURE VIEW APP.SV_SO_LINE AS
  WITH promises AS (
    SELECT LINE_ID, MAX_BY(PROMISE_ON, REVISION) AS LATEST_PROMISE_ON, COUNT_IF(KIND = 'REVISED') AS PROMISE_REVISIONS
    FROM CORE.PROMISE_REVISION WHERE WORLD_ID = 'MERIDIAN' GROUP BY LINE_ID
  )
  SELECT s.LINE_ID AS SO_LINE_ID, s.CUSTOMER_ID, s.ITEM_ID, s.FACILITY_ID, s.GEOGRAPHY_ID, s.ORDERED_QTY, s.ORDER_ON,
         s.ORIGINAL_PROMISE_ON, DATE_TRUNC('month', s.ORIGINAL_PROMISE_ON) AS PROMISE_MONTH, p.LATEST_PROMISE_ON,
         COALESCE(p.PROMISE_REVISIONS, 0) AS PROMISE_REVISIONS, s.CANCELLATION, s.HOLD_START, s.HOLD_END, s.SUBSTITUTE, s.INCOTERM
  FROM CORE.SO_LINE s LEFT JOIN promises p ON p.LINE_ID = s.LINE_ID
  WHERE s.WORLD_ID = 'MERIDIAN';
CREATE OR REPLACE SECURE VIEW APP.SV_PROMISE AS
  SELECT p.LINE_ID || '#' || p.REVISION AS PROMISE_KEY, p.LINE_ID AS SO_LINE_ID, s.FACILITY_ID, p.REVISION, p.KIND AS PROMISE_KIND,
         p.PROMISE_ON, p.RECORDED_ON
  FROM CORE.PROMISE_REVISION p JOIN CORE.SO_LINE s ON s.WORLD_ID = p.WORLD_ID AND s.LINE_ID = p.LINE_ID
  WHERE p.WORLD_ID = 'MERIDIAN';
CREATE OR REPLACE SECURE VIEW APP.SV_SHIPMENT AS
  WITH events AS (
    SELECT SHIPMENT_ID, MAX(IFF(KIND = 'POD', EVENT_ON, NULL)) AS DELIVERED_ON, COUNT_IF(KIND = 'ATTEMPT') AS FAILED_ATTEMPTS,
           COUNT_IF(KIND = 'MISDELIVERY') AS MISDELIVERIES
    FROM CORE.SO_DELIVERY_EVENT WHERE WORLD_ID = 'MERIDIAN' GROUP BY SHIPMENT_ID
  )
  SELECT s.SHIP_ID AS SHIPMENT_ID, s.LINE_ID AS SO_LINE_ID, s.FACILITY_ID, s.SHIP_ON, s.QTY AS SHIPPED_QTY, s.SHIPPED_ITEM_ID,
         e.DELIVERED_ON, COALESCE(e.FAILED_ATTEMPTS, 0) AS FAILED_ATTEMPTS, COALESCE(e.MISDELIVERIES, 0) AS MISDELIVERIES
  FROM CORE.SO_SHIPMENT s LEFT JOIN events e ON e.SHIPMENT_ID = s.SHIP_ID
  WHERE s.WORLD_ID = 'MERIDIAN';
CREATE OR REPLACE SECURE VIEW APP.SV_ALLOCATION AS
  SELECT LOT_ID, SOURCE_ID AS SHIPMENT_ID, FACILITY_ID, QTY AS ALLOCATED_QTY, EVENT_TIME FROM CORE.LOT_TRACE WHERE SOURCE_TYPE = 'SHIPMENT';

-- ---------------------------------------------------------------- cost masking (Snowflake masking policies)
-- A real role that holds CONCORDIA_COST_READER sees cost. The Streamlit app runs as CONCORDIA_APP_OWNER and records
-- the chosen persona for this session; the policy reads that row. A persona role never gets cost from the session row.
CREATE TABLE IF NOT EXISTS GOV.APP_PERSONA_CONTEXT (SESSION_ID VARCHAR PRIMARY KEY, PERSONA VARCHAR, SET_AT TIMESTAMP_TZ);
CREATE MASKING POLICY IF NOT EXISTS GOV.COST_VALUE_MASK AS (VAL NUMBER(38,12), METRIC VARCHAR) RETURNS NUMBER(38,12) -> VAL;
CREATE MASKING POLICY IF NOT EXISTS GOV.COST_TEXT_MASK AS (VAL VARCHAR, METRIC VARCHAR) RETURNS VARCHAR -> VAL;
ALTER MASKING POLICY GOV.COST_VALUE_MASK SET BODY ->
  CASE WHEN METRIC IS DISTINCT FROM 'LANDED_COST_PER_ACCEPTED_UNIT' THEN VAL
       WHEN IS_ROLE_IN_SESSION('CONCORDIA_COST_READER') THEN VAL
       WHEN IS_ROLE_IN_SESSION('CONCORDIA_APP_OWNER') AND EXISTS (
         SELECT 1 FROM CONCORDIA.GOV.APP_PERSONA_CONTEXT c
         WHERE c.SESSION_ID = CURRENT_SESSION() AND c.PERSONA IN ('PROCUREMENT', 'EXECUTIVE', 'AUDITOR')) THEN VAL
       ELSE NULL END;
ALTER MASKING POLICY GOV.COST_TEXT_MASK SET BODY ->
  CASE WHEN METRIC IS DISTINCT FROM 'LANDED_COST_PER_ACCEPTED_UNIT' THEN VAL
       WHEN IS_ROLE_IN_SESSION('CONCORDIA_COST_READER') THEN VAL
       WHEN IS_ROLE_IN_SESSION('CONCORDIA_APP_OWNER') AND EXISTS (
         SELECT 1 FROM CONCORDIA.GOV.APP_PERSONA_CONTEXT c
         WHERE c.SESSION_ID = CURRENT_SESSION() AND c.PERSONA IN ('PROCUREMENT', 'EXECUTIVE', 'AUDITOR')) THEN VAL
       ELSE NULL END;
ALTER VIEW APP.SV_RESULT MODIFY COLUMN VALUE_NUM SET MASKING POLICY GOV.COST_VALUE_MASK USING (VALUE_NUM, METRIC_ID) FORCE;
ALTER VIEW APP.SV_RESULT MODIFY COLUMN DISPLAY SET MASKING POLICY GOV.COST_TEXT_MASK USING (DISPLAY, METRIC_ID) FORCE;
ALTER VIEW APP.SV_RESULT MODIFY COLUMN NUMERATOR SET MASKING POLICY GOV.COST_TEXT_MASK USING (NUMERATOR, METRIC_ID) FORCE;
ALTER VIEW APP.SV_RESULT MODIFY COLUMN DENOMINATOR SET MASKING POLICY GOV.COST_TEXT_MASK USING (DENOMINATOR, METRIC_ID) FORCE;
ALTER VIEW APP.SV_RECEIPT_COST MODIFY COLUMN AMOUNT SET MASKING POLICY GOV.COST_VALUE_MASK USING (AMOUNT, COST_METRIC) FORCE;

-- ---------------------------------------------------------------- site entitlement (Snowflake row access policy)
-- A persona whose GOV.ENTITLEMENT.ALLOWED_FACILITIES excludes a site does not see that site's rows. Rows with no site
-- (network, part, region, supplier and customer answers) stay visible: they are aggregates, not site records.
CREATE ROW ACCESS POLICY IF NOT EXISTS GOV.SITE_ACCESS AS (FAC VARCHAR) RETURNS BOOLEAN -> TRUE;
ALTER ROW ACCESS POLICY GOV.SITE_ACCESS SET BODY ->
  FAC IS NULL
  OR IS_ROLE_IN_SESSION('CONCORDIA_ADMIN')
  OR EXISTS (
    SELECT 1 FROM CONCORDIA.GOV.ENTITLEMENT e
    WHERE (ARRAY_CONTAINS('*'::VARIANT, e.ALLOWED_FACILITIES) OR ARRAY_CONTAINS(FAC::VARIANT, e.ALLOWED_FACILITIES))
      AND IFF(IS_ROLE_IN_SESSION('CONCORDIA_APP_OWNER'),
              e.PERSONA = (SELECT MAX(c.PERSONA) FROM CONCORDIA.GOV.APP_PERSONA_CONTEXT c WHERE c.SESSION_ID = CURRENT_SESSION()),
              IS_ROLE_IN_SESSION('CONCORDIA_' || e.PERSONA)));
ALTER VIEW APP.SV_RESULT ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_LINE_OUTCOME ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_PO_LINE ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_RECEIPT ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_RECEIPT_COST ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_RECEIPT_LOT ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_SO_LINE ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_PROMISE ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_SHIPMENT ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_ALLOCATION ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_IOT_LOT ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);
ALTER VIEW APP.SV_CONSUMPTION ADD ROW ACCESS POLICY GOV.SITE_ACCESS ON (FACILITY_ID);

-- ---------------------------------------------------------------- the semantic view
CREATE OR REPLACE SEMANTIC VIEW APP.SUPPLY_CHAIN_ONTOLOGY
  TABLES (
    results AS CONCORDIA.APP.SV_RESULT PRIMARY KEY (RESULT_KEY)
      WITH SYNONYMS = ('governed answers', 'kpis', 'published metrics')
      COMMENT = 'One row per governed answer: metric x month x known-as-of x scope, computed by the CORE metric functions. Synthetic data.',
    parts AS CONCORDIA.APP.SV_PART PRIMARY KEY (ITEM_ID)
      WITH SYNONYMS = ('items', 'products', 'skus', 'motors', 'components')
      COMMENT = 'Canonical parts. Motors (MM-4xx) are finished goods we sell; components (CP-, SA-) are bought or built into motors.',
    sites AS CONCORDIA.APP.SV_SITE PRIMARY KEY (FACILITY_ID)
      WITH SYNONYMS = ('facilities', 'plants', 'factories', 'warehouses', 'distribution centres', 'dcs')
      COMMENT = 'Plants (Dayton, Reno, Stuttgart) and distribution centres (Newark, Oakland, Hamburg).',
    regions AS CONCORDIA.APP.SV_REGION PRIMARY KEY (GEOGRAPHY_ID)
      WITH SYNONYMS = ('geographies', 'customer regions', 'territories', 'markets')
      COMMENT = 'Customer ship-to regions, each in one country.',
    suppliers AS CONCORDIA.APP.SV_SUPPLIER PRIMARY KEY (SUPPLIER_ID)
      WITH SYNONYMS = ('vendors', 'sellers')
      COMMENT = 'Canonical supplier companies resolved across ERP, WMS and TMS keys.',
    customers AS CONCORDIA.APP.SV_CUSTOMER PRIMARY KEY (CUSTOMER_ID)
      WITH SYNONYMS = ('accounts', 'buyers', 'clients')
      COMMENT = 'Canonical customer companies resolved across ERP, TMS and CRM keys.',
    metric_contracts AS CONCORDIA.APP.SV_METRIC PRIMARY KEY (METRIC_ID)
      WITH SYNONYMS = ('definitions', 'metric definitions', 'contracts')
      COMMENT = 'The written, versioned and hashed definition of each governed metric.',
    supply_links AS CONCORDIA.APP.SV_SUPPLY PRIMARY KEY (SUPPLIER_ID, ITEM_ID)
      COMMENT = 'Ontology relationship SUPPLIES: supplier supplies part.',
    bill_of_materials AS CONCORDIA.APP.SV_BOM PRIMARY KEY (PARENT_ITEM_ID, COMPONENT_ITEM_ID)
      WITH SYNONYMS = ('bom', 'recipe', 'components of')
      COMMENT = 'Ontology relationship COMPONENT_OF: component part goes into a parent motor or sub-assembly.',
    capabilities AS CONCORDIA.APP.SV_CAPABILITY PRIMARY KEY (FACILITY_ID, ITEM_ID)
      COMMENT = 'Ontology relationship CAPABLE_OF_PRODUCING: plant can make part.',
    sourcing AS CONCORDIA.APP.SV_SOURCING PRIMARY KEY (MOTOR_ID, COMPONENT_ITEM_ID, SUPPLIER_ID)
      WITH SYNONYMS = ('supply path', 'who supplies the components of', 'sourcing tree', 'supplier to motor')
      COMMENT = 'Cross-domain path supplier -> SUPPLIES -> component -> COMPONENT_OF (any BOM level) -> motor. Use for questions linking suppliers to the motors they feed.',
    flow_trace AS CONCORDIA.APP.SV_FLOW_TRACE
      WITH SYNONYMS = ('end to end supply chain', 'supplier to customer path', 'cross domain trace')
      COMMENT = 'Product-level ontology path Supplier -> Component -> Motor -> home Plant -> Customer -> Region. This is not order- or lot-specific genealogy.',
    iot_lots AS CONCORDIA.APP.SV_IOT_LOT PRIMARY KEY (EVENT_ID)
      WITH SYNONYMS = ('dock sensors', 'truck arrivals', 'temperature telemetry', 'lots', 'lot genealogy')
      COMMENT = 'Synthetic IoT dock events tied to receipt and shipment lots, items and sites.',
    substitutions AS CONCORDIA.APP.SV_SUBSTITUTION PRIMARY KEY (ITEM_ID, SUBSTITUTE_ITEM_ID, VALID_FROM)
      WITH SYNONYMS = ('approved alternatives', 'substitute parts')
      COMMENT = 'Effective-dated SUBSTITUTES_FOR relationships approved by the change board.',
    consumption AS CONCORDIA.APP.SV_CONSUMPTION PRIMARY KEY (ISSUE_ID)
      WITH SYNONYMS = ('material issues', 'components consumed by production')
      COMMENT = 'CONSUMES relationships from production orders to component lots.',
    line_outcomes AS CONCORDIA.APP.SV_LINE_OUTCOME PRIMARY KEY (OUTCOME_KEY)
      WITH SYNONYMS = ('order line outcomes', 'missed lines', 'why it missed', 'late lines', 'root cause', 'drivers')
      COMMENT = 'The order lines counted in each governed supplier OTD, customer OTD and fill-rate answer, from the same publish run: hit, miss or excluded, and the stored cause. Use for why questions.',
    purchase_orders AS CONCORDIA.APP.SV_PO_LINE PRIMARY KEY (PO_LINE_ID)
      WITH SYNONYMS = ('purchase order lines', 'po lines', 'pos', 'inbound orders')
      COMMENT = 'Purchase order lines (ERP): what we ordered from which supplier, for which part and site, and when it was due.',
    receipts AS CONCORDIA.APP.SV_RECEIPT PRIMARY KEY (RECEIPT_ID)
      WITH SYNONYMS = ('goods receipts', 'grs', 'deliveries from suppliers')
      COMMENT = 'Goods receipts (WMS) against a purchase order line: FULFILLS. Reach part, site and supplier through purchase_orders.',
    receipt_costs AS CONCORDIA.APP.SV_RECEIPT_COST PRIMARY KEY (COST_DOCUMENT_ID)
      WITH SYNONYMS = ('cost documents', 'freight bills', 'duty bills', 'invoices', 'landed cost components')
      COMMENT = 'Cost documents (merchandise, freight, duty, insurance, brokerage, credits) attached to a receipt: COST_OF. Amounts are masked for personas without cost access.',
    receipt_lots AS CONCORDIA.APP.SV_RECEIPT_LOT PRIMARY KEY (LOT_ID)
      WITH SYNONYMS = ('received lots', 'inbound lots')
      COMMENT = 'Lots created by a goods receipt: CONTAINS.',
    sales_orders AS CONCORDIA.APP.SV_SO_LINE PRIMARY KEY (SO_LINE_ID)
      WITH SYNONYMS = ('sales order lines', 'customer orders', 'so lines', 'outbound orders')
      COMMENT = 'Customer order lines (ERP/CRM) with the original promise date, latest promise date and number of promise revisions.',
    promises AS CONCORDIA.APP.SV_PROMISE PRIMARY KEY (PROMISE_KEY)
      WITH SYNONYMS = ('promise dates', 'promise revisions', 'commitments')
      COMMENT = 'Every promise made on a customer order line: PROMISES. Revision 1 is the original; customer OTD always measures the original.',
    shipments AS CONCORDIA.APP.SV_SHIPMENT PRIMARY KEY (SHIPMENT_ID)
      WITH SYNONYMS = ('shipments', 'deliveries to customers', 'proof of delivery', 'pods')
      COMMENT = 'Shipments (TMS) against a customer order line with the proof-of-delivery date, failed attempts and misdeliveries.',
    allocations AS CONCORDIA.APP.SV_ALLOCATION PRIMARY KEY (LOT_ID)
      WITH SYNONYMS = ('lot allocations', 'shipped lots', 'which lots went to which order')
      COMMENT = 'ALLOCATED_TO: finished lot allocated to a customer order line, derived from the shipment that carried it.'
  )
  RELATIONSHIPS (
    result_part AS results (ITEM_ID) REFERENCES parts,
    result_site AS results (FACILITY_ID) REFERENCES sites,
    result_region AS results (GEOGRAPHY_ID) REFERENCES regions,
    result_supplier AS results (SUPPLIER_ID) REFERENCES suppliers,
    result_customer AS results (CUSTOMER_ID) REFERENCES customers,
    result_contract AS results (METRIC_ID) REFERENCES metric_contracts,
    supply_supplier AS supply_links (SUPPLIER_ID) REFERENCES suppliers,
    supply_part AS supply_links (ITEM_ID) REFERENCES parts,
    bom_parent AS bill_of_materials (PARENT_ITEM_ID) REFERENCES parts,
    bom_component AS bill_of_materials (COMPONENT_ITEM_ID) REFERENCES parts,
    capability_site AS capabilities (FACILITY_ID) REFERENCES sites,
    capability_part AS capabilities (ITEM_ID) REFERENCES parts,
    sourcing_supplier AS sourcing (SUPPLIER_ID) REFERENCES suppliers,
    sourcing_component AS sourcing (COMPONENT_ITEM_ID) REFERENCES parts,
    iot_part AS iot_lots (ITEM_ID) REFERENCES parts,
    iot_site AS iot_lots (FACILITY_ID) REFERENCES sites,
    outcome_part AS line_outcomes (ITEM_ID) REFERENCES parts,
    outcome_site AS line_outcomes (FACILITY_ID) REFERENCES sites,
    outcome_region AS line_outcomes (GEOGRAPHY_ID) REFERENCES regions,
    outcome_supplier AS line_outcomes (SUPPLIER_ID) REFERENCES suppliers,
    outcome_customer AS line_outcomes (CUSTOMER_ID) REFERENCES customers,
    outcome_contract AS line_outcomes (METRIC_ID) REFERENCES metric_contracts,
    po_part AS purchase_orders (ITEM_ID) REFERENCES parts,
    po_site AS purchase_orders (FACILITY_ID) REFERENCES sites,
    po_supplier AS purchase_orders (SUPPLIER_ID) REFERENCES suppliers,
    receipt_po AS receipts (PO_LINE_ID) REFERENCES purchase_orders,
    cost_receipt AS receipt_costs (RECEIPT_ID) REFERENCES receipts,
    lot_receipt AS receipt_lots (RECEIPT_ID) REFERENCES receipts,
    so_part AS sales_orders (ITEM_ID) REFERENCES parts,
    so_site AS sales_orders (FACILITY_ID) REFERENCES sites,
    so_region AS sales_orders (GEOGRAPHY_ID) REFERENCES regions,
    so_customer AS sales_orders (CUSTOMER_ID) REFERENCES customers,
    promise_so AS promises (SO_LINE_ID) REFERENCES sales_orders,
    shipment_so AS shipments (SO_LINE_ID) REFERENCES sales_orders,
    allocation_shipment AS allocations (SHIPMENT_ID) REFERENCES shipments
  )
  FACTS (
    PRIVATE results.inbound_value AS IFF(METRIC_ID = 'INBOUND_SUPPLIER_OTD', VALUE_NUM, NULL),
    PRIVATE results.outbound_value AS IFF(METRIC_ID = 'OUTBOUND_CUSTOMER_OTD', VALUE_NUM, NULL),
    PRIVATE results.fill_value AS IFF(METRIC_ID = 'UNIT_FILL_RATE', VALUE_NUM, NULL),
    PRIVATE results.inventory_value AS IFF(METRIC_ID = 'DAYS_INVENTORY', VALUE_NUM, NULL),
    PRIVATE results.landed_value AS IFF(METRIC_ID = 'LANDED_COST_PER_ACCEPTED_UNIT', VALUE_NUM, NULL),
    PRIVATE results.published_value AS VALUE_NUM,
    PRIVATE results.answer_key AS RESULT_KEY,
    PRIVATE results.inbound_key AS IFF(METRIC_ID = 'INBOUND_SUPPLIER_OTD', RESULT_KEY, NULL),
    PRIVATE results.outbound_key AS IFF(METRIC_ID = 'OUTBOUND_CUSTOMER_OTD', RESULT_KEY, NULL),
    PRIVATE results.fill_key AS IFF(METRIC_ID = 'UNIT_FILL_RATE', RESULT_KEY, NULL),
    PRIVATE results.inventory_key AS IFF(METRIC_ID = 'DAYS_INVENTORY', RESULT_KEY, NULL),
    PRIVATE results.landed_key AS IFF(METRIC_ID = 'LANDED_COST_PER_ACCEPTED_UNIT', RESULT_KEY, NULL),
    PRIVATE line_outcomes.outcome_ref AS OUTCOME_KEY,
    PRIVATE line_outcomes.miss_flag AS IS_MISS,
    PRIVATE line_outcomes.hit_flag AS IS_HIT,
    PRIVATE line_outcomes.excluded_flag AS IS_EXCLUDED,
    line_outcomes.line_qty AS QTY COMMENT = 'Units ordered on the line.',
    PRIVATE purchase_orders.po_ref AS PO_LINE_ID,
    purchase_orders.ordered_units AS ORDERED_QTY COMMENT = 'Units ordered on the purchase order line.',
    PRIVATE receipts.receipt_ref AS RECEIPT_ID,
    receipts.accepted_units AS ACCEPTED_QTY COMMENT = 'Units accepted on the goods receipt.',
    PRIVATE receipt_costs.cost_ref AS COST_DOCUMENT_ID,
    PRIVATE receipt_lots.received_lot_ref AS LOT_ID,
    PRIVATE sales_orders.so_ref AS SO_LINE_ID,
    sales_orders.customer_ordered_units AS ORDERED_QTY COMMENT = 'Units the customer ordered.',
    PRIVATE promises.promise_ref AS PROMISE_KEY,
    PRIVATE shipments.shipment_ref AS SHIPMENT_ID,
    shipments.shipped_units AS SHIPPED_QTY COMMENT = 'Units on the shipment.',
    PRIVATE allocations.allocated_lot_ref AS LOT_ID,
    PRIVATE supply_links.supplier_ref AS SUPPLIER_ID,
    PRIVATE supply_links.part_ref AS ITEM_ID,
    PRIVATE capabilities.part_ref AS ITEM_ID,
    PRIVATE sourcing.supplier_ref AS SUPPLIER_ID,
    PRIVATE sourcing.component_ref AS COMPONENT_ITEM_ID,
    PRIVATE flow_trace.supplier_ref AS SUPPLIER_ID,
    PRIVATE flow_trace.customer_ref AS CUSTOMER_ID,
    PRIVATE flow_trace.motor_ref AS MOTOR_ID,
    PRIVATE iot_lots.event_ref AS EVENT_ID,
    PRIVATE substitutions.substitute_ref AS SUBSTITUTE_ITEM_ID,
    PRIVATE consumption.issue_ref AS ISSUE_ID,
    PRIVATE consumption.consumed_qty AS QTY,
    bill_of_materials.quantity_per_parent AS QTY_PER COMMENT = 'Units of the component used in one parent.'
  )
  DIMENSIONS (
    results.metric_id AS METRIC_ID
      COMMENT = 'INBOUND_SUPPLIER_OTD, OUTBOUND_CUSTOMER_OTD, UNIT_FILL_RATE, DAYS_INVENTORY, LANDED_COST_PER_ACCEPTED_UNIT.',
    results.month AS PERIOD_START WITH SYNONYMS = ('period', 'month start', 'reporting month')
      COMMENT = 'First day of the measured calendar month.',
    results.known_as_of AS AS_OF_KIND WITH SYNONYMS = ('as of', 'known when', 'early or final', 'version of the answer')
      COMMENT = 'final = what is known on the latest load (15 Jul 2026); early = what was known on the 5th of the following month.',
    results.as_of_timestamp AS AS_OF COMMENT = 'The exact recorded-as-of timestamp of the answer.',
    results.scope_level AS SCOPE_LEVEL WITH SYNONYMS = ('grain', 'level')
      COMMENT = 'NETWORK, PART, PART_SITE, PART_REGION, SITE, REGION, SUPPLIER or CUSTOMER. Each governed answer exists at exactly one scope level.',
    results.status AS STATUS
      COMMENT = 'COMPLETE, INCOMPLETE (inputs missing, not final), ABSTAIN, ZERO_DENOMINATOR (nothing due), ZERO_DEMAND.',
    results.governed_value_text AS DISPLAY WITH SYNONYMS = ('display value', 'reported value')
      COMMENT = 'The governed value as text, 4 decimals half-even. Null when withheld (incomplete landed cost or masked).',
    results.counted AS NUMERATOR WITH SYNONYMS = ('numerator', 'on time count', 'units shipped')
      COMMENT = 'Numerator as text: on-time lines, shipped units, available units x 28, or landed cents.',
    results.out_of AS DENOMINATOR WITH SYNONYMS = ('denominator', 'lines due', 'units ordered')
      COMMENT = 'Denominator as text: lines due, units ordered, 28-day demand, or accepted units.',
    results.coverage AS COVERAGE COMMENT = 'Share of the scope whose inputs were complete, 0 to 1, as text.',
    results.reasons AS REASONS COMMENT = 'Machine-readable reasons the answer is not final, comma separated.',
    parts.part_id AS ITEM_ID WITH SYNONYMS = ('part number', 'item id', 'sku', 'motor id')
      COMMENT = 'Canonical part id, for example MM-440 or CP-1019.',
    parts.part_name AS PART_NAME WITH SYNONYMS = ('part description', 'product name'),
    parts.part_type AS PART_TYPE COMMENT = 'Motor (finished good we sell) or Component (bought or sub-assembly).',
    parts.product_family AS FAMILY WITH SYNONYMS = ('family', 'product line', 'series')
      COMMENT = 'Part hierarchy: motors roll up to families MM-40x ... MM-44x; components to their commodity.',
    parts.home_site_id AS HOME_FACILITY_ID COMMENT = 'Plant that normally makes or receives the part.',
    sites.site_id AS FACILITY_ID WITH SYNONYMS = ('facility id', 'plant id'),
    sites.site_name AS SITE_NAME WITH SYNONYMS = ('plant', 'facility', 'warehouse', 'dc'),
    sites.site_type AS SITE_TYPE COMMENT = 'Plant or Distribution centre.',
    sites.site_country AS COUNTRY COMMENT = 'Site hierarchy: site rolls up to country.',
    regions.region_id AS GEOGRAPHY_ID,
    regions.region_name AS REGION_NAME WITH SYNONYMS = ('region', 'geography', 'market'),
    regions.region_country AS COUNTRY COMMENT = 'Region hierarchy: region rolls up to country.',
    suppliers.supplier_id AS SUPPLIER_ID,
    suppliers.supplier_name AS SUPPLIER_NAME WITH SYNONYMS = ('vendor', 'supplier'),
    suppliers.supplier_country AS COUNTRY,
    suppliers.parent_company_id AS PARENT_PARTY_ID COMMENT = 'Supplier hierarchy: parent company, when one exists.',
    customers.customer_id AS CUSTOMER_ID,
    customers.customer_name AS CUSTOMER_NAME WITH SYNONYMS = ('customer', 'account'),
    customers.customer_country AS COUNTRY,
    customers.customer_region_id AS CUSTOMER_REGION_ID,
    metric_contracts.measure_id AS METRIC_ID,
    metric_contracts.measure_name AS DISPLAY_NAME WITH SYNONYMS = ('metric name', 'kpi name'),
    metric_contracts.business_question AS QUESTION,
    metric_contracts.owner_team AS OWNER WITH SYNONYMS = ('owner', 'accountable team'),
    metric_contracts.approver AS APPROVER,
    metric_contracts.definition_version AS METRIC_VERSION,
    metric_contracts.definition_hash AS DEFINITION_HASH,
    metric_contracts.computed_by AS RESULT_FUNCTION,
    bill_of_materials.parent_part_id AS PARENT_ITEM_ID WITH SYNONYMS = ('assembly', 'parent motor'),
    sourcing.fed_motor_id AS MOTOR_ID WITH SYNONYMS = ('motor fed', 'finished motor', 'end product')
      COMMENT = 'Finished motor that the supplied component ends up in.',
    sourcing.via_component_id AS COMPONENT_ITEM_ID WITH SYNONYMS = ('through component', 'supplied component', 'via part')
      COMMENT = 'The bought part the supplier provides on the path to the motor. Join parts for its name.',
    sourcing.bom_level AS BOM_LEVEL COMMENT = '0 = the motor itself is bought complete from this supplier; 1 = component goes straight into the motor; 2+ = goes into a sub-assembly first.'
    ,flow_trace.supplier_name AS SUPPLIER_NAME,
    flow_trace.component_id AS COMPONENT_ITEM_ID,
    flow_trace.component_name AS COMPONENT_NAME,
    flow_trace.motor_id AS MOTOR_ID,
    flow_trace.motor_name AS MOTOR_NAME,
    flow_trace.plant_id AS FACILITY_ID,
    flow_trace.plant_name AS FACILITY_NAME,
    flow_trace.customer_id AS CUSTOMER_ID,
    flow_trace.customer_name AS CUSTOMER_NAME,
    flow_trace.region_id AS GEOGRAPHY_ID,
    flow_trace.region_name AS REGION_NAME,
    flow_trace.bom_level AS BOM_LEVEL,
    iot_lots.iot_event_id AS EVENT_ID,
    iot_lots.sensor_id AS SENSOR_ID,
    iot_lots.sensor_event_type AS EVENT_TYPE,
    iot_lots.sensor_event_time AS EVENT_TIME,
    iot_lots.truck_id AS TRUCK_ID,
    iot_lots.lot_id AS LOT_ID,
    iot_lots.item_id AS ITEM_ID,
    iot_lots.item_name AS ITEM_NAME,
    iot_lots.facility_id AS FACILITY_ID,
    iot_lots.facility_name AS FACILITY_NAME,
    iot_lots.receipt_id AS RECEIPT_ID,
    iot_lots.shipment_id AS SHIPMENT_ID,
    iot_lots.temperature_c AS TEMPERATURE_C,
    substitutions.original_item_id AS ITEM_ID,
    substitutions.substitute_item_id AS SUBSTITUTE_ITEM_ID,
    substitutions.valid_from AS VALID_FROM,
    substitutions.valid_to AS VALID_TO,
    substitutions.approved_by AS APPROVED_BY,
    consumption.production_order_id AS ORDER_ID,
    consumption.component_item_id AS COMPONENT_ID,
    consumption.lot_id AS LOT_ID,
    consumption.issued_on AS ISSUED_ON,
    line_outcomes.metric_id AS METRIC_ID
      COMMENT = 'INBOUND_SUPPLIER_OTD, OUTBOUND_CUSTOMER_OTD or UNIT_FILL_RATE: the governed answer this line counted towards.',
    line_outcomes.known_as_of AS AS_OF_KIND COMMENT = 'final or early, as for results.known_as_of.',
    line_outcomes.order_line_id AS LINE_ID WITH SYNONYMS = ('order line', 'line id')
      COMMENT = 'Purchase order line for supplier OTD; customer order line for customer OTD and fill rate.',
    line_outcomes.month AS PERIOD_START COMMENT = 'First day of the month the line was due in (same month as the governed answer).',
    line_outcomes.due_on AS DUE_ON COMMENT = 'The commitment date the line was measured against.',
    line_outcomes.outcome AS OUTCOME COMMENT = 'HIT (on time and complete), MISS, or EXCLUDED (data could not be trusted).',
    line_outcomes.cause_code AS CAUSE_CODE
      COMMENT = 'Stored miss driver: LATE_RECEIPT, PARTIAL_RECEIPT, SUPPLIER_REJECT, LATE_DELIVERY, PARTIAL_DELIVERY, FAILED_OR_MISDELIVERED, PROMISE_REVISED, NOT_SHIPPED, SILENT_SUBSTITUTE and others.',
    line_outcomes.cause AS CAUSE WITH SYNONYMS = ('reason', 'why', 'root cause', 'driver') COMMENT = 'The stored cause in plain English.',
    line_outcomes.exclusion_reasons AS REASONS COMMENT = 'Why an EXCLUDED line was left out, comma separated.',
    line_outcomes.commitment_on AS COMMITMENT_ON,
    line_outcomes.completed_on AS COMPLETED_ON,
    purchase_orders.po_line_id AS PO_LINE_ID WITH SYNONYMS = ('po line', 'purchase order'),
    purchase_orders.issued_on AS ISSUED_ON,
    purchase_orders.requested_on AS BUYER_REQUESTED_ON,
    purchase_orders.supplier_promise_on AS ACK_PROMISE_ON COMMENT = 'Date the supplier acknowledged and promised.',
    purchase_orders.due_month AS DUE_MONTH COMMENT = 'Month the line was due (supplier promise, else requested date). Descriptive only; the governed metric applies its own rules.',
    purchase_orders.first_receipt_on AS FIRST_RECEIPT_ON,
    purchase_orders.po_incoterm AS INCOTERM,
    purchase_orders.po_cancellation AS CANCELLATION,
    receipts.receipt_id AS RECEIPT_ID WITH SYNONYMS = ('goods receipt', 'gr'),
    receipts.received_on AS RECEIVED_ON,
    receipts.accepted_on AS ACCEPTED_ON,
    receipts.accepted_month AS ACCEPTED_MONTH COMMENT = 'Month the receipt was accepted; landed cost per accepted unit is measured by this month.',
    receipts.origin_country AS ORIGIN_COUNTRY,
    receipt_costs.cost_document_id AS COST_DOCUMENT_ID,
    receipt_costs.cost_kind AS COST_KIND WITH SYNONYMS = ('cost type', 'charge type')
      COMMENT = 'MERCHANDISE, FREIGHT, DUTY, INSURANCE, BROKERAGE or CREDIT.',
    receipt_costs.source_document_id AS SOURCE_DOCUMENT_ID COMMENT = 'Invoice or bill number in the source system.',
    receipt_costs.currency AS CURRENCY,
    receipt_costs.cost_amount AS AMOUNT
      COMMENT = 'Cost document amount in its own currency. Masked for personas without cost access; null when the bill is not in yet. Never sum across currencies.',
    receipt_costs.amount_state AS AMOUNT_STATE COMMENT = 'Amount known or Amount not in yet.',
    receipt_costs.invoice_date AS INVOICE_DATE,
    receipt_lots.lot_id AS LOT_ID,
    receipt_lots.received_qty AS QTY,
    sales_orders.so_line_id AS SO_LINE_ID WITH SYNONYMS = ('sales order line', 'customer order line', 'order line'),
    sales_orders.order_on AS ORDER_ON,
    sales_orders.original_promise_on AS ORIGINAL_PROMISE_ON COMMENT = 'The first promise date; customer OTD measures this one.',
    sales_orders.promise_month AS PROMISE_MONTH COMMENT = 'Month of the original promise date.',
    sales_orders.latest_promise_on AS LATEST_PROMISE_ON,
    sales_orders.promise_revisions AS PROMISE_REVISIONS COMMENT = 'Number of times the promise date was moved.',
    sales_orders.so_cancellation AS CANCELLATION,
    sales_orders.substitute AS SUBSTITUTE COMMENT = 'Substitute part shipped, if any.',
    promises.revision AS REVISION,
    promises.promise_kind AS PROMISE_KIND COMMENT = 'ORIGINAL or REVISED.',
    promises.promise_on AS PROMISE_ON,
    promises.recorded_on AS RECORDED_ON,
    shipments.shipment_id AS SHIPMENT_ID,
    shipments.ship_on AS SHIP_ON,
    shipments.delivered_on AS DELIVERED_ON COMMENT = 'Proof-of-delivery date.',
    shipments.failed_attempts AS FAILED_ATTEMPTS,
    shipments.misdeliveries AS MISDELIVERIES,
    shipments.shipped_item_id AS SHIPPED_ITEM_ID,
    allocations.lot_id AS LOT_ID,
    allocations.allocated_qty AS ALLOCATED_QTY
  )
  METRICS (
    results.supplier_on_time_delivery AS IFF(COUNT(results.inbound_key) = 1, MAX(results.inbound_value), NULL)
      WITH SYNONYMS = ('inbound OTD', 'inbound supplier OTD', 'supplier OTD', 'supplier on-time rate', 'vendor on-time delivery')
      COMMENT = 'Governed share (0-1) of purchase order lines delivered in full by the supplier commitment date. Returns the published answer only when exactly one matches; otherwise null. Filter scope_level, known_as_of and month.',
    results.customer_on_time_delivery AS IFF(COUNT(results.outbound_key) = 1, MAX(results.outbound_value), NULL)
      WITH SYNONYMS = ('outbound OTD', 'outbound customer OTD', 'customer OTD', 'delivery to customers on time')
      COMMENT = 'Governed share (0-1) of customer order lines delivered complete by the original promise date. Null unless exactly one published answer matches.',
    results.unit_fill_rate AS IFF(COUNT(results.fill_key) = 1, MAX(results.fill_value), NULL)
      WITH SYNONYMS = ('fill rate', 'unit fill', 'share of units shipped')
      COMMENT = 'Governed share (0-1) of ordered units shipped, regardless of timing. Null unless exactly one published answer matches.',
    results.days_of_inventory AS IFF(COUNT(results.inventory_key) = 1, MAX(results.inventory_value), NULL)
      WITH SYNONYMS = ('days inventory', 'days of supply', 'days of cover', 'inventory days on hand')
      COMMENT = 'Governed days of usable finished-goods stock against trailing 28-day demand, at a snapshot. Null unless exactly one published answer matches.',
    results.landed_cost_per_unit AS IFF(COUNT(results.landed_key) = 1, MAX(results.landed_value), NULL)
      WITH SYNONYMS = ('landed cost', 'landed cost per accepted unit', 'cost per accepted unit')
      COMMENT = 'Governed USD per accepted unit including freight, duty, insurance and brokerage less credits. Null when INCOMPLETE, masked, or more than one answer matches.',
    results.governed_value AS IFF(COUNT(results.answer_key) = 1, MAX(results.published_value), NULL)
      COMMENT = 'The published value for the metric identified by results.metric_id, null unless exactly one answer matches. Use for side-by-side comparisons of different governed metrics.',
    results.governed_answer_count AS COUNT(results.answer_key)
      COMMENT = 'Number of governed answers matched. Diagnostic only, not a business metric.',
    supply_links.supplier_count AS COUNT(DISTINCT supply_links.supplier_ref)
      WITH SYNONYMS = ('number of suppliers', 'how many suppliers')
      COMMENT = 'Distinct suppliers linked by the SUPPLIES relationship.',
    supply_links.supplied_part_count AS COUNT(DISTINCT supply_links.part_ref)
      COMMENT = 'Distinct parts linked by the SUPPLIES relationship.',
    sourcing.feeding_supplier_count AS COUNT(DISTINCT sourcing.supplier_ref)
      WITH SYNONYMS = ('suppliers behind a motor', 'number of suppliers feeding')
      COMMENT = 'Distinct suppliers whose parts end up in the selected motors.',
    sourcing.sourced_component_count AS COUNT(DISTINCT sourcing.component_ref)
      COMMENT = 'Distinct bought components in the selected motors.',
    flow_trace.supplier_count AS COUNT(DISTINCT flow_trace.supplier_ref)
      COMMENT = 'Distinct suppliers on the selected end-to-end paths.',
    flow_trace.customer_count AS COUNT(DISTINCT flow_trace.customer_ref)
      COMMENT = 'Distinct customers on the selected end-to-end paths.',
    flow_trace.motor_count AS COUNT(DISTINCT flow_trace.motor_ref)
      COMMENT = 'Distinct finished motors on the selected end-to-end paths.',
    iot_lots.iot_event_count AS COUNT(DISTINCT iot_lots.event_ref)
      COMMENT = 'Distinct synthetic IoT dock events.',
    substitutions.substitute_count AS COUNT(DISTINCT substitutions.substitute_ref)
      COMMENT = 'Distinct approved substitute parts.',
    consumption.consumed_quantity AS SUM(consumption.consumed_qty)
      COMMENT = 'Component quantity consumed by production orders.',
    capabilities.producible_part_count AS COUNT(DISTINCT capabilities.part_ref)
      COMMENT = 'Distinct parts a site can produce.',
    bill_of_materials.component_quantity AS SUM(bill_of_materials.quantity_per_parent)
      COMMENT = 'Total component units per parent across the selected bill-of-materials lines.',
    line_outcomes.counted_lines AS COUNT(line_outcomes.outcome_ref)
      COMMENT = 'Order lines counted towards the governed answer (hits, misses and exclusions).',
    line_outcomes.missed_lines AS SUM(line_outcomes.miss_flag) WITH SYNONYMS = ('misses', 'late lines')
      COMMENT = 'Order lines that missed. A count of stored outcomes, not a governed rate.',
    line_outcomes.on_time_lines AS SUM(line_outcomes.hit_flag) COMMENT = 'Order lines on time and complete.',
    line_outcomes.excluded_lines AS SUM(line_outcomes.excluded_flag) COMMENT = 'Order lines left out because their data could not be trusted.',
    purchase_orders.po_line_count AS COUNT(purchase_orders.po_ref) COMMENT = 'Purchase order lines.',
    purchase_orders.units_ordered_from_suppliers AS SUM(purchase_orders.ordered_units),
    receipts.receipt_count AS COUNT(receipts.receipt_ref) COMMENT = 'Goods receipts.',
    receipts.units_accepted AS SUM(receipts.accepted_units),
    receipt_costs.cost_document_count AS COUNT(receipt_costs.cost_ref) COMMENT = 'Cost documents.',
    receipt_lots.received_lot_count AS COUNT(receipt_lots.received_lot_ref),
    sales_orders.so_line_count AS COUNT(sales_orders.so_ref) COMMENT = 'Customer order lines.',
    sales_orders.units_ordered_by_customers AS SUM(sales_orders.customer_ordered_units),
    promises.promise_count AS COUNT(promises.promise_ref),
    shipments.shipment_count AS COUNT(shipments.shipment_ref),
    shipments.units_shipped AS SUM(shipments.shipped_units),
    allocations.allocated_lot_count AS COUNT(allocations.allocated_lot_ref)
  )
  COMMENT = 'Concordia supply chain ontology (synthetic Meridian Motion). Governed metric values come only from the CORE metric functions via the published grid.'
  AI_SQL_GENERATION 'Always write SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS ... DIMENSIONS ... WHERE ...) with an optional ORDER BY outside; never query the semantic view with FROM, GROUP BY or AGG(). Every governed answer is one pre-computed row in results. Always filter results.metric_id to the governed metric ids asked about (INBOUND_SUPPLIER_OTD, OUTBOUND_CUSTOMER_OTD, UNIT_FILL_RATE, DAYS_INVENTORY, LANDED_COST_PER_ACCEPTED_UNIT), using IN for several, and include results.metric_id as a dimension. Always filter results.scope_level to exactly one value that matches the question: NETWORK for the whole business; PART for one part across all sites and regions; PART_SITE for a part at a site; PART_REGION for a part in a customer region; SITE, REGION, SUPPLIER or CUSTOMER when only that is named. Always filter results.known_as_of: use ''final'' unless the user asks what was known early, at the time, or on the 5th of the next month, then use ''early''. Never average, sum, subtract or otherwise recompute governed metrics across rows, months or scopes; to compare, return the rows side by side ordered by month. Months are first-of-month dates in results.month. Always return results.status and results.governed_value_text next to any governed metric. Days of inventory is a point-in-time snapshot published for every finished motor represented in inventory at site and part/network scopes: for final use month 2026-07-01, for early use the month asked. If a landed cost row has status INCOMPLETE its value is null by contract; report the status and reasons and do not substitute any number. Match parts by parts.part_id when an id like MM-440 or CP-1019 is given. For which suppliers feed a motor, or through which components, answer with SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS suppliers.supplier_name, sourcing.via_component_id, parts.part_name, sourcing.bom_level WHERE sourcing.fed_motor_id = <motor>) without governed metrics; parts here is the supplied component. Questions that only list or count ontology entities may use DIMENSIONS and the count metrics without filtering results. For why a governed OTD or fill rate missed, list line_outcomes (order_line_id, outcome, cause_code, cause, due_on, completed_on) filtered by line_outcomes.metric_id, line_outcomes.known_as_of, line_outcomes.month and the same part, site or region; these are the exact lines counted in the published answer. For order, receipt, shipment, promise, cost document or lot questions use purchase_orders, receipts, receipt_costs, receipt_lots, sales_orders, promises, shipments and allocations as DIMENSIONS with their count metrics; they are descriptive records, never a governed rate, and must not be divided or averaged into one. Do not combine promises with shipments or allocations in one query (they are separate branches of sales_orders); use sales_orders.original_promise_on, latest_promise_on and promise_revisions instead. Landed cost months are receipts.accepted_month.'
  AI_QUESTION_CATEGORIZATION 'If the user says OTD or on-time delivery without also saying supplier, inbound, vendor, customer or outbound, consider the question UNCLEAR and ask whether they mean supplier on-time delivery or customer on-time delivery. Do not answer with both and do not guess. If the user says cost without saying landed cost, consider the question UNCLEAR and ask whether they mean landed cost per accepted unit. If the user asks about OTIF, on time in full, perfect order, shipping on time, customer rating, satisfaction, NPS, or merchandise plus outbound freight, reject the question: it is not a governed Concordia metric. Name the five governed metrics: supplier on-time delivery, customer on-time delivery, unit fill rate, days of inventory, landed cost per accepted unit. Questions about anything other than the synthetic Meridian Motion supply chain are out of scope.'
  AI_VERIFIED_QUERIES (
    vq_01 AS (QUESTION 'Why did outbound customer OTD for MM-440 change in May 2026?' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS customer_on_time_delivery DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id, regions.region_name WHERE results.metric_id = ''OUTBOUND_CUSTOMER_OTD'' AND results.scope_level = ''PART_REGION'' AND results.known_as_of = ''final'' AND results.month IN (''2026-04-01'', ''2026-05-01'') AND parts.part_id = ''MM-440'' AND regions.region_name = ''Northeast'')'),
    vq_02 AS (QUESTION 'Inbound supplier OTD for MM-440 at Dayton in May 2026' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS supplier_on_time_delivery DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id, sites.site_name WHERE results.metric_id = ''INBOUND_SUPPLIER_OTD'' AND results.scope_level = ''PART_SITE'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'' AND parts.part_id = ''MM-440'' AND sites.site_name = ''Dayton'')'),
    vq_03 AS (QUESTION 'Outbound customer OTD for MM-440 in the Northeast in May 2026' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS customer_on_time_delivery DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id, regions.region_name WHERE results.metric_id = ''OUTBOUND_CUSTOMER_OTD'' AND results.scope_level = ''PART_REGION'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'' AND parts.part_id = ''MM-440'' AND regions.region_name = ''Northeast'')'),
    vq_04 AS (QUESTION 'Unit fill rate for MM-440 in May 2026' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS unit_fill_rate DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id WHERE results.metric_id = ''UNIT_FILL_RATE'' AND results.scope_level = ''PART'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'' AND parts.part_id = ''MM-440'')'),
    vq_05 AS (QUESTION 'Days inventory of MM-440 finished goods at Dayton' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS days_of_inventory DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id, sites.site_name WHERE results.metric_id = ''DAYS_INVENTORY'' AND results.scope_level = ''PART_SITE'' AND results.known_as_of = ''final'' AND results.month = ''2026-07-01'' AND parts.part_id = ''MM-440'' AND sites.site_name = ''Dayton'')'),
    vq_06 AS (QUESTION 'Landed cost per accepted unit for MM-440 at Dayton in May 2026' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS landed_cost_per_unit DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id, sites.site_name WHERE results.metric_id = ''LANDED_COST_PER_ACCEPTED_UNIT'' AND results.scope_level = ''PART_SITE'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'' AND parts.part_id = ''MM-440'' AND sites.site_name = ''Dayton'')'),
    vq_07 AS (QUESTION 'Landed cost for MM-440 at Dayton in May 2026 as known on 5 June' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS landed_cost_per_unit DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, results.reasons, parts.part_id, sites.site_name WHERE results.metric_id = ''LANDED_COST_PER_ACCEPTED_UNIT'' AND results.scope_level = ''PART_SITE'' AND results.known_as_of = ''early'' AND results.month = ''2026-05-01'' AND parts.part_id = ''MM-440'' AND sites.site_name = ''Dayton'')'),
    vq_08 AS (QUESTION 'Compare landed cost for MM-440 at Dayton in May 2026 between 5 June and 15 July' ONBOARDING_QUESTION TRUE VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS landed_cost_per_unit DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, results.reasons, parts.part_id, sites.site_name WHERE results.metric_id = ''LANDED_COST_PER_ACCEPTED_UNIT'' AND results.scope_level = ''PART_SITE'' AND results.known_as_of IN (''early'', ''final'') AND results.month = ''2026-05-01'' AND parts.part_id = ''MM-440'' AND sites.site_name = ''Dayton'')'),
    vq_09 AS (QUESTION 'Outbound customer OTD by region for May 2026' ONBOARDING_QUESTION TRUE VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS customer_on_time_delivery DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, regions.region_name WHERE results.metric_id = ''OUTBOUND_CUSTOMER_OTD'' AND results.scope_level = ''REGION'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'')'),
    vq_10 AS (QUESTION 'Inbound supplier OTD trend for Dayton' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS supplier_on_time_delivery DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, sites.site_name WHERE results.metric_id = ''INBOUND_SUPPLIER_OTD'' AND results.scope_level = ''SITE'' AND results.known_as_of = ''final'' AND sites.site_name = ''Dayton'')'),
    vq_11 AS (QUESTION 'Network days inventory for MM-440 finished goods' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS days_of_inventory DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id WHERE results.metric_id = ''DAYS_INVENTORY'' AND results.scope_level = ''PART'' AND results.known_as_of = ''final'' AND results.month = ''2026-07-01'' AND parts.part_id = ''MM-440'')'),
    vq_12 AS (QUESTION 'Unit fill rate by region for May 2026' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS unit_fill_rate DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, regions.region_name WHERE results.metric_id = ''UNIT_FILL_RATE'' AND results.scope_level = ''REGION'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'')'),
    vq_13 AS (QUESTION 'Compare supplier on-time delivery, customer on-time delivery and fill rate for MM-440 in May 2026' ONBOARDING_QUESTION TRUE VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS governed_value DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, parts.part_id WHERE results.metric_id IN (''INBOUND_SUPPLIER_OTD'', ''OUTBOUND_CUSTOMER_OTD'', ''UNIT_FILL_RATE'') AND results.scope_level = ''PART'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'' AND parts.part_id = ''MM-440'')'),
    vq_14 AS (QUESTION 'Which suppliers feed motor MM-401, and through which components?' ONBOARDING_QUESTION TRUE VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS suppliers.supplier_name, sourcing.via_component_id, parts.part_name, sourcing.bom_level WHERE sourcing.fed_motor_id = ''MM-401'')'),
    vq_15 AS (QUESTION 'Show the product-level supplier, component, home plant, customer and region paths for motor MM-401' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS flow_trace.supplier_name, flow_trace.component_id, flow_trace.component_name, flow_trace.motor_id, flow_trace.plant_name, flow_trace.customer_name, flow_trace.region_name, flow_trace.bom_level WHERE flow_trace.motor_id = ''MM-401'')'),
    vq_16 AS (QUESTION 'Show IoT dock events and lots for MM-440 at Dayton' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS iot_lots.iot_event_id, iot_lots.sensor_id, iot_lots.sensor_event_type, iot_lots.sensor_event_time, iot_lots.truck_id, iot_lots.lot_id, iot_lots.item_id, iot_lots.facility_name, iot_lots.temperature_c WHERE iot_lots.item_id = ''MM-440'' AND iot_lots.facility_name = ''Dayton'')'),
    vq_17 AS (QUESTION 'Which MM-440 order lines in the Northeast missed customer on-time delivery in May 2026, and why?' ONBOARDING_QUESTION TRUE VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS line_outcomes.order_line_id, line_outcomes.metric_id, line_outcomes.month, line_outcomes.known_as_of, line_outcomes.outcome, line_outcomes.cause_code, line_outcomes.cause, line_outcomes.due_on, line_outcomes.completed_on, customers.customer_name, parts.part_id, regions.region_name WHERE line_outcomes.metric_id = ''OUTBOUND_CUSTOMER_OTD'' AND line_outcomes.known_as_of = ''final'' AND line_outcomes.month = ''2026-05-01'' AND line_outcomes.outcome = ''MISS'' AND parts.part_id = ''MM-440'' AND regions.region_name = ''Northeast'')'),
    vq_18 AS (QUESTION 'Trace the MM-440 sales order lines, promise dates, shipments and lots for the Northeast in May 2026' ONBOARDING_QUESTION TRUE VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS sales_orders.so_line_id, customers.customer_name, sales_orders.original_promise_on, sales_orders.latest_promise_on, sales_orders.promise_revisions, shipments.shipment_id, shipments.ship_on, shipments.delivered_on, shipments.failed_attempts, shipments.misdeliveries, allocations.lot_id, allocations.allocated_qty, parts.part_id, regions.region_name WHERE parts.part_id = ''MM-440'' AND regions.region_name = ''Northeast'' AND sales_orders.promise_month = ''2026-05-01'')'),
    vq_19 AS (QUESTION 'Show the MM-440 purchase order lines, receipts and lots at Dayton in May 2026' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS purchase_orders.po_line_id, suppliers.supplier_name, purchase_orders.supplier_promise_on, receipts.receipt_id, receipts.received_on, receipts.accepted_on, receipt_lots.lot_id, receipt_lots.received_qty, parts.part_id, sites.site_name WHERE parts.part_id = ''MM-440'' AND sites.site_name = ''Dayton'' AND purchase_orders.due_month = ''2026-05-01'')'),
    vq_20 AS (QUESTION 'Which cost documents make up landed cost for MM-440 receipts at Dayton in May 2026?' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY DIMENSIONS receipts.receipt_id, receipts.accepted_on, receipt_costs.cost_document_id, receipt_costs.cost_kind, receipt_costs.source_document_id, receipt_costs.currency, receipt_costs.cost_amount, receipt_costs.amount_state, parts.part_id, sites.site_name WHERE parts.part_id = ''MM-440'' AND sites.site_name = ''Dayton'' AND receipts.accepted_month = ''2026-05-01'')'),
    vq_21 AS (QUESTION 'Customer on-time delivery by site for May 2026' VERIFIED_BY '(STEWARD = concordia)' SQL
      'SELECT * FROM SEMANTIC_VIEW(CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY METRICS customer_on_time_delivery DIMENSIONS results.metric_id, results.month, results.scope_level, results.known_as_of, results.status, results.governed_value_text, sites.site_name WHERE results.metric_id = ''OUTBOUND_CUSTOMER_OTD'' AND results.scope_level = ''SITE'' AND results.known_as_of = ''final'' AND results.month = ''2026-05-01'')')
  );


-- ---------------------------------------------------------------- guarded execution of Cortex Analyst SQL
CREATE OR REPLACE PROCEDURE APP.RUN_SEMANTIC_SQL(P_PERSONA VARCHAR, P_SQL VARCHAR)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
EXECUTE AS CALLER
AS
$$
import json
import re
from decimal import Decimal

VIEW = "CONCORDIA.APP.SUPPLY_CHAIN_ONTOLOGY"
GOVERNED = {"SUPPLIER_ON_TIME_DELIVERY": "INBOUND_SUPPLIER_OTD", "CUSTOMER_ON_TIME_DELIVERY": "OUTBOUND_CUSTOMER_OTD",
            "UNIT_FILL_RATE": "UNIT_FILL_RATE", "DAYS_OF_INVENTORY": "DAYS_INVENTORY",
            "LANDED_COST_PER_UNIT": "LANDED_COST_PER_ACCEPTED_UNIT", "GOVERNED_VALUE": "_DYNAMIC_"}
FORBIDDEN_WORDS = r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|GRANT|REVOKE|CALL|COPY|PUT|GET|EXECUTE|USE|SET|UNSET|TRUNCATE|UNDROP|REMOVE|LIST)\b"


def strip(sql):
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return sql.strip().rstrip(";").strip()


def outside_semantic_call(sql):
    upper = sql.upper()
    start = upper.find("SEMANTIC_VIEW(")
    if start < 0:
        return None
    depth, i = 0, start + len("SEMANTIC_VIEW")
    while i < len(sql):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[:start] + sql[i + 1:], sql[start:i + 1]
        i += 1
    return None


def no_literals(text):
    return re.sub(r"'(?:[^']|'')*'", "''", text)


def check(sql):
    if not re.match(r"^(SELECT|WITH)\b", sql, re.I):
        return "Only SELECT statements are allowed."
    if ";" in no_literals(sql):
        return "Only one statement is allowed."
    if re.search(FORBIDDEN_WORDS, no_literals(sql).upper()):
        return "Statement contains a forbidden keyword."
    parts = outside_semantic_call(sql)
    if parts is None:
        return f"The query must read the governed semantic view {VIEW} through SEMANTIC_VIEW()."
    outer, inner = parts
    refs = {m.upper() for m in re.findall(r"\b[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*\.[A-Za-z_][A-Za-z0-9_$]*\b", no_literals(sql))}
    if refs - {VIEW}:
        return "The query may only reference " + VIEW + "; found " + ", ".join(sorted(refs - {VIEW})) + "."
    if VIEW not in no_literals(inner).upper():
        return f"SEMANTIC_VIEW() must name {VIEW}."
    outer_clean = re.sub(r"(?i)select\s+\*", "SELECT", no_literals(outer))
    if re.search(r"(?i)\b(AVG|SUM|MEDIAN|STDDEV|VARIANCE|RATIO_TO_REPORT|PERCENTILE_CONT)\s*\(", outer_clean) or re.search(r"[*/+]", outer_clean):
        return "Governed metrics may not be re-aggregated or recomputed outside the semantic view."
    if "SEMANTIC_VIEW(" in no_literals(inner).upper()[len("SEMANTIC_VIEW("):]:
        return "Nested semantic view calls are not allowed."
    metrics_clause = re.search(r"(?is)\bMETRICS\b(.*?)(\bDIMENSIONS\b|\bFACTS\b|\bWHERE\b|\)\s*$)", no_literals(inner))
    names = metrics_clause.group(1).upper() if metrics_clause else ""
    if any(m in names for m in GOVERNED) and not re.search(r"(?i)\bmetric_id\s*(=|\bIN\b)", sql):
        return "A governed metric query must filter results.metric_id so each value is paired with its own metric."
    return None


def plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


COLUMN_FOR = {metric: column for column, metric in GOVERNED.items() if metric != "_DYNAMIC_"}
FILTERS = {
    "metric": ("r.METRIC_ID", r"results\.metric_id"),
    "scope": ("r.SCOPE_LEVEL", r"results\.scope_level"),
    "as_of": ("r.AS_OF_KIND", r"results\.known_as_of"),
    "month": ("r.PERIOD_START", r"results\.month"),
    "item": ("r.ITEM_ID", r"parts\.part_id"),
    "site_id": ("r.FACILITY_ID", r"sites\.site_id"),
    "site_name": ("site.SITE_NAME", r"sites\.site_name"),
    "region_id": ("r.GEOGRAPHY_ID", r"regions\.region_id"),
    "region_name": ("region.REGION_NAME", r"regions\.region_name"),
    "supplier_id": ("r.SUPPLIER_ID", r"suppliers\.supplier_id"),
    "supplier_name": ("supplier.SUPPLIER_NAME", r"suppliers\.supplier_name"),
    "customer_id": ("r.CUSTOMER_ID", r"customers\.customer_id"),
    "customer_name": ("customer.CUSTOMER_NAME", r"customers\.customer_name"),
}
RESULT_COL = {
    "metric": "METRIC_ID", "scope": "SCOPE_LEVEL", "as_of": "KNOWN_AS_OF", "month": "MONTH", "item": "PART_ID",
    "site_id": "SITE_ID", "site_name": "SITE_NAME", "region_id": "REGION_ID", "region_name": "REGION_NAME",
    "supplier_id": "SUPPLIER_ID", "supplier_name": "SUPPLIER_NAME", "customer_id": "CUSTOMER_ID", "customer_name": "CUSTOMER_NAME",
}
EXPECTED_COL = {
    "metric": "METRIC_ID", "scope": "SCOPE_LEVEL", "as_of": "AS_OF_KIND", "month": "MONTH", "item": "ITEM_ID",
    "site_id": "FACILITY_ID", "site_name": "SITE_NAME", "region_id": "GEOGRAPHY_ID", "region_name": "REGION_NAME",
    "supplier_id": "SUPPLIER_ID", "supplier_name": "SUPPLIER_NAME", "customer_id": "CUSTOMER_ID", "customer_name": "CUSTOMER_NAME",
}
NOTES = {
    "VERIFIED": "Each number equals the governed answer published for that metric, month, known-as-of and scope. Nothing was recalculated.",
    "UNVERIFIED": "These rows are not exactly the published answers for that scope, so they are not shown.",
    "UNPINNED": "The query did not pin metric, scope, known-as-of and month, so it cannot be checked against one published answer.",
    "DESCRIPTIVE": "No governed metric in this result: these are descriptive facts about the ontology.",
}


def literals(sql, expr):
    found = []
    equal = re.search(expr + r"\s*=\s*'([^']*)'", sql, re.I)
    if equal:
        found.append(equal.group(1))
    group = re.search(expr + r"\s+IN\s*\(([^)]*)\)", sql, re.I)
    if group:
        found.extend(re.findall(r"'([^']*)'", group.group(1)))
    unique = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique


def as_text(value):
    return None if value is None else str(value)


def as_month(value):
    return None if value is None else str(value)[:10]


def as_num(value):
    return None if value is None else round(float(value), 9)


def prove(session, cleaned, columns, rows):
    inner = outside_semantic_call(cleaned)[1]
    where = re.search(r"(?is)\bWHERE\b(.*)$", inner)
    if where and re.search(r"(?i)\b(OR|NOT|LIKE|ILIKE|BETWEEN|RLIKE)\b", where.group(1)):
        return "UNPINNED", "The filters are too complex to prove which published row each value came from.", 0, []
    metrics_clause = re.search(r"(?is)\bMETRICS\b(.*?)(\bDIMENSIONS\b|\bFACTS\b|\bWHERE\b|\)\s*$)", inner)
    names = metrics_clause.group(1).upper() if metrics_clause else ""
    if not any(column in names for column in GOVERNED):
        return "DESCRIPTIVE", None, 0, []
    picked = {name: literals(inner, expr) for name, (column, expr) in FILTERS.items()}
    upper = [c.upper() for c in columns]
    active = [name for name, col in RESULT_COL.items() if picked[name] or col in upper]
    if any(name not in active for name in ("metric", "scope", "as_of", "month")):
        return "UNPINNED", NOTES["UNPINNED"], 0, []
    if not any(picked.values()):
        return "UNPINNED", NOTES["UNPINNED"], 0, []
    clauses, binds = [], []
    for name, values in picked.items():
        if values:
            clauses.append(FILTERS[name][0] + " IN (" + ",".join(["?"] * len(values)) + ")")
            binds.extend(values)
    found = session.sql(
        "SELECT r.METRIC_ID, r.SCOPE_LEVEL, r.AS_OF_KIND, TO_VARCHAR(r.PERIOD_START) AS MONTH, r.ITEM_ID, r.FACILITY_ID, "
        "site.SITE_NAME, r.GEOGRAPHY_ID, region.REGION_NAME, r.SUPPLIER_ID, supplier.SUPPLIER_NAME, r.CUSTOMER_ID, "
        "customer.CUSTOMER_NAME, r.STATUS, r.VALUE_NUM FROM CONCORDIA.APP.SV_RESULT r "
        "LEFT JOIN CONCORDIA.APP.SV_SITE site ON site.FACILITY_ID = r.FACILITY_ID "
        "LEFT JOIN CONCORDIA.APP.SV_REGION region ON region.GEOGRAPHY_ID = r.GEOGRAPHY_ID "
        "LEFT JOIN CONCORDIA.APP.SV_SUPPLIER supplier ON supplier.SUPPLIER_ID = r.SUPPLIER_ID "
        "LEFT JOIN CONCORDIA.APP.SV_CUSTOMER customer ON customer.CUSTOMER_ID = r.CUSTOMER_ID WHERE " + " AND ".join(clauses),
        params=binds).collect()
    expected = {}
    for item in found:
        key = tuple(as_month(item[EXPECTED_COL[name]]) if name == "month" else as_text(item[EXPECTED_COL[name]]) for name in active)
        if key in expected:
            return "UNPINNED", "The columns returned do not uniquely identify each published answer.", 0, []
        expected[key] = (as_num(item["VALUE_NUM"]), item["STATUS"])
    index = {c.upper(): i for i, c in enumerate(columns)}
    seen, governed_cols = {}, []
    for row in rows:
        resolved = {}
        for name in active:
            col = RESULT_COL[name]
            if col in index and row[index[col]] is not None:
                resolved[name] = as_month(row[index[col]]) if name == "month" else str(row[index[col]])
            elif len(picked[name]) == 1:
                resolved[name] = picked[name][0]
            else:
                return "UNPINNED", "A result row does not identify one published answer.", 0, governed_cols
        metric = resolved["metric"]
        value_column = "GOVERNED_VALUE" if "GOVERNED_VALUE" in index else COLUMN_FOR.get(metric)
        if value_column is None or value_column not in index:
            return "UNVERIFIED", "The result does not carry the governed value for " + metric + ".", 0, governed_cols
        if value_column not in governed_cols:
            governed_cols.append(value_column)
        key = tuple(resolved[name] for name in active)
        if key in seen:
            return "UNPINNED", "Two result rows identify the same published answer.", 0, governed_cols
        status = row[index["STATUS"]] if "STATUS" in index else None
        seen[key] = (as_num(row[index[value_column]]), status)
    if set(seen) != set(expected):
        return "UNVERIFIED", NOTES["UNVERIFIED"], len(seen), governed_cols
    for key, (value, status) in seen.items():
        exp_value, exp_status = expected[key]
        if value != exp_value or (status is not None and status != exp_status):
            return "UNVERIFIED", "A value does not equal the published answer for that exact scope.", len(seen), governed_cols
    return "VERIFIED", None, len(seen), governed_cols


def run(session, persona, sql):
    entitled = session.sql("SELECT COST_VISIBLE FROM CONCORDIA.GOV.ENTITLEMENT WHERE PERSONA = ?", params=[persona]).collect()
    if not entitled:
        return {"verdict": "REJECTED", "reason": "Unknown persona."}
    cost_visible = bool(entitled[0]["COST_VISIBLE"])
    cleaned = strip(sql or "")
    problem = check(cleaned)
    if problem:
        return {"verdict": "REJECTED", "reason": problem, "sql": cleaned}
    session.sql(
        "MERGE INTO CONCORDIA.GOV.APP_PERSONA_CONTEXT t USING (SELECT CURRENT_SESSION() AS SESSION_ID, ? AS PERSONA) s "
        "ON t.SESSION_ID = s.SESSION_ID WHEN MATCHED THEN UPDATE SET PERSONA = s.PERSONA, SET_AT = CURRENT_TIMESTAMP() "
        "WHEN NOT MATCHED THEN INSERT (SESSION_ID, PERSONA, SET_AT) VALUES (s.SESSION_ID, s.PERSONA, CURRENT_TIMESTAMP())",
        params=[persona]).collect()
    frame = session.sql(cleaned).limit(500).collect()
    columns = list(frame[0].as_dict().keys()) if frame else []
    rows = [[plain(v) for v in r.as_dict().values()] for r in frame]
    asks_cost = bool(re.search(r"(?i)landed_cost|LANDED_COST_PER_ACCEPTED_UNIT|landed_value", cleaned))
    if asks_cost and not cost_visible:
        return {"verdict": "WITHHELD", "sql": cleaned, "columns": columns, "rows": [], "governed_columns": [],
                "checked_values": 0, "unmatched": [], "row_count": len(rows), "cost_masked": True,
                "note": "Landed cost is governed but hidden for this persona by the Snowflake masking policy."}
    verdict, reason, checked, governed_cols = prove(session, cleaned, columns, rows)
    note = reason or NOTES[verdict]
    amounts_masked = bool(re.search(r"(?i)receipt_costs\.cost_amount\b", cleaned)) and not cost_visible
    if amounts_masked:
        note += " Cost document amounts are hidden for this persona by the Snowflake masking policy."
    return {"verdict": verdict, "sql": cleaned, "columns": columns, "rows": rows, "governed_columns": governed_cols,
            "checked_values": checked, "unmatched": [], "row_count": len(rows), "cost_masked": amounts_masked,
            "note": note}
$$;

CREATE OR REPLACE PROCEDURE APP.AUDIT_SEMANTIC(
  P_PERSONA VARCHAR, P_QUESTION VARCHAR, P_ROUTE VARCHAR, P_CLARIFICATION VARCHAR,
  P_SQL VARCHAR, P_STATUS VARCHAR, P_DETAIL VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
  audit_id VARCHAR DEFAULT UUID_STRING();
BEGIN
  INSERT INTO GOV.QUERY_AUDIT
    (AUDIT_ID, SNOWFLAKE_USER, SNOWFLAKE_ROLE, PERSONA, QUESTION, NORMALIZED, ROUTE, CLARIFICATION,
     SEMANTIC_OBJECT, SQL_HASH, QUERY_ID, MODEL, STATUS, DETAIL)
  SELECT :audit_id, CURRENT_USER(), CURRENT_ROLE(), :P_PERSONA, :P_QUESTION, LOWER(TRIM(:P_QUESTION)), :P_ROUTE,
         :P_CLARIFICATION, 'APP.SUPPLY_CHAIN_ONTOLOGY', SHA2(COALESCE(:P_SQL, '')), LAST_QUERY_ID(),
         'cortex-analyst', :P_STATUS, TRY_PARSE_JSON(:P_DETAIL);
  RETURN :audit_id;
END;
$$;

UPDATE GOV.MODEL_PIN SET NOTE = 'Cortex Analyst reads APP.SUPPLY_CHAIN_ONTOLOGY, including its verified queries. Generated SQL is allowlisted, then each value is checked against the published row for that metric, month, known-as-of and scope. Landed cost is hidden by the masking policy.'
WHERE PURPOSE = 'ANALYST';

-- ---------------------------------------------------------------- grants
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_PLANNER;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_PROCUREMENT;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_LOGISTICS;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_EXECUTIVE;
GRANT USAGE ON DATABASE CONCORDIA TO ROLE CONCORDIA_AUDITOR;
GRANT USAGE ON SCHEMA CONCORDIA.APP TO ROLE CONCORDIA_PLANNER;
GRANT USAGE ON SCHEMA CONCORDIA.APP TO ROLE CONCORDIA_PROCUREMENT;
GRANT USAGE ON SCHEMA CONCORDIA.APP TO ROLE CONCORDIA_LOGISTICS;
GRANT USAGE ON SCHEMA CONCORDIA.APP TO ROLE CONCORDIA_EXECUTIVE;
GRANT USAGE ON SCHEMA CONCORDIA.APP TO ROLE CONCORDIA_AUDITOR;
EXECUTE IMMEDIATE $$
DECLARE
  roles ARRAY DEFAULT ARRAY_CONSTRUCT('CONCORDIA_PLANNER', 'CONCORDIA_PROCUREMENT', 'CONCORDIA_LOGISTICS', 'CONCORDIA_EXECUTIVE',
                                      'CONCORDIA_AUDITOR', 'CONCORDIA_APP_OWNER');
  views ARRAY DEFAULT ARRAY_CONSTRUCT('SV_RESULT', 'SV_PART', 'SV_SITE', 'SV_REGION', 'SV_SUPPLIER', 'SV_CUSTOMER', 'SV_METRIC',
                                      'SV_SUPPLY', 'SV_BOM', 'SV_CAPABILITY', 'SV_SOURCING', 'SV_FLOW_TRACE', 'SV_IOT_LOT',
                                      'SV_SUBSTITUTION', 'SV_CONSUMPTION', 'SV_LINE_OUTCOME', 'SV_PO_LINE', 'SV_RECEIPT',
                                      'SV_RECEIPT_COST', 'SV_RECEIPT_LOT', 'SV_SO_LINE', 'SV_PROMISE', 'SV_SHIPMENT', 'SV_ALLOCATION');
BEGIN
  FOR i IN 0 TO ARRAY_SIZE(roles) - 1 DO
    FOR j IN 0 TO ARRAY_SIZE(views) - 1 DO
      EXECUTE IMMEDIATE 'GRANT SELECT ON VIEW CONCORDIA.APP.' || views[j] || ' TO ROLE ' || roles[i];
    END FOR;
  END FOR;
  RETURN 'granted';
END;
$$;
GRANT SELECT ON SEMANTIC VIEW APP.SUPPLY_CHAIN_ONTOLOGY TO ROLE CONCORDIA_PLANNER;
GRANT SELECT ON SEMANTIC VIEW APP.SUPPLY_CHAIN_ONTOLOGY TO ROLE CONCORDIA_PROCUREMENT;
GRANT SELECT ON SEMANTIC VIEW APP.SUPPLY_CHAIN_ONTOLOGY TO ROLE CONCORDIA_LOGISTICS;
GRANT SELECT ON SEMANTIC VIEW APP.SUPPLY_CHAIN_ONTOLOGY TO ROLE CONCORDIA_EXECUTIVE;
GRANT SELECT ON SEMANTIC VIEW APP.SUPPLY_CHAIN_ONTOLOGY TO ROLE CONCORDIA_AUDITOR;
GRANT SELECT ON SEMANTIC VIEW APP.SUPPLY_CHAIN_ONTOLOGY TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON PROCEDURE APP.RUN_SEMANTIC_SQL(VARCHAR, VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON PROCEDURE APP.AUDIT_SEMANTIC(VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR, VARCHAR) TO ROLE CONCORDIA_APP_OWNER;
GRANT USAGE ON SCHEMA GOV TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT ON TABLE GOV.ENTITLEMENT TO ROLE CONCORDIA_APP_OWNER;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE GOV.APP_PERSONA_CONTEXT TO ROLE CONCORDIA_APP_OWNER;
