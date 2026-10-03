-- Golden evaluation worlds. Each golden case is loaded into CORE under WORLD_ID 'EVAL:<case id>'
-- so the SQL metric functions can be checked against the frozen fixtures. Product APP views filter
-- WORLD_ID = 'MERIDIAN' and never expose these rows.

USE ROLE CONCORDIA_ADMIN;
USE WAREHOUSE CONCORDIA_WH;
USE DATABASE CONCORDIA;

CREATE OR REPLACE PROCEDURE CORE.LOAD_EVAL_WORLDS()
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
  CREATE OR REPLACE TEMPORARY TABLE CORE.EVAL_CASE AS
    SELECT 'EVAL:' || c.value:id::VARCHAR AS W, c.value AS C, c.index AS CI
    FROM (SELECT $1 AS DOC FROM @LAND.WORLD_STAGE/eval_cases.json (FILE_FORMAT => 'LAND.JSON_FMT')) d, LATERAL FLATTEN(d.DOC) c;

  DELETE FROM CORE.PO_LINE WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.PO_ACCEPTANCE WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.SO_LINE WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.SO_DELIVERY_EVENT WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.SO_SHIPMENT WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.PROMISE_REVISION WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.INVENTORY_SNAPSHOT WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.DEMAND_EVENT WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.WORLD_FACILITY WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.RECEIPT WHERE WORLD_ID LIKE 'EVAL:%';
  DELETE FROM CORE.COST_COMPONENT WHERE WORLD_ID LIKE 'EVAL:%';

  INSERT INTO CORE.PO_LINE
    SELECT e.W, l.value:line_id, l.value:supplier_id, l.value:item_id, l.value:facility_id, l.value:timezone, l.value:calendar:id,
           l.value:ordered_qty::NUMBER(38,6), l.value:issued_on::DATE, l.value:buyer_requested_on::DATE, l.value:ack_on::DATE,
           l.value:ack_promise_on::DATE, l.value:ack_visible_at::TIMESTAMP_TZ, l.value:first_receipt_on::DATE, l.value:cancellation,
           l.value:supplier_rejected_qty::NUMBER(38,6), NULL, l.value:identity_resolved::BOOLEAN, l.value:uom_resolved::BOOLEAN,
           l.value:timezone_resolved::BOOLEAN, l.value:disposition_missing::BOOLEAN, l.value:visible_at::TIMESTAMP_TZ, 'golden', l.index
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:lines) l WHERE e.C:metric_id = 'INBOUND_SUPPLIER_OTD';
  INSERT INTO CORE.PO_ACCEPTANCE
    SELECT e.W, l.value:line_id || '#' || a.index, l.value:line_id, NULL, a.value:on::DATE, a.value:qty::NUMBER(38,6),
           a.value:visible_at::TIMESTAMP_TZ, l.index * 1000 + a.index
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:lines) l, LATERAL FLATTEN(l.value:accepted) a WHERE e.C:metric_id = 'INBOUND_SUPPLIER_OTD';

  INSERT INTO CORE.SO_LINE
    SELECT e.W, l.value:line_id, l.value:customer_id, NULL, l.value:item_id, l.value:facility_id, l.value:geography_id, l.value:timezone,
           l.value:calendar:id, l.value:incoterm, l.value:ordered_qty::NUMBER(38,6), NULL, l.value:requested_ship_on::DATE,
           l.value:original_promise_on::DATE, l.value:cancellation, l.value:substitute, l.value:hold_start::DATE, l.value:hold_end::DATE,
           l.value:hold_recorded_on::DATE, l.value:short_close_qty::NUMBER(38,6), l.value:short_close_approved_on::DATE,
           l.value:identity_resolved::BOOLEAN, l.value:uom_resolved::BOOLEAN, l.value:visible_at::TIMESTAMP_TZ, 'golden', l.index
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:lines) l WHERE e.C:metric_id IN ('OUTBOUND_CUSTOMER_OTD', 'UNIT_FILL_RATE');
  INSERT INTO CORE.SO_DELIVERY_EVENT
    SELECT e.W, l.value:line_id || '#' || v.index, l.value:line_id, NULL, v.value:kind, v.value:on::DATE, v.value:qty::NUMBER(38,6), NULL,
           v.value:visible_at::TIMESTAMP_TZ, l.index * 1000 + v.index
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:lines) l, LATERAL FLATTEN(l.value:events) v WHERE e.C:metric_id = 'OUTBOUND_CUSTOMER_OTD';
  INSERT INTO CORE.SO_SHIPMENT
    SELECT e.W, l.value:line_id || '#ship', l.value:line_id, NULL, l.value:ship_confirmed_qty::NUMBER(38,6), l.value:item_id, l.value:facility_id,
           l.value:ship_visible_at::TIMESTAMP_TZ
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:lines) l
    WHERE e.C:metric_id = 'UNIT_FILL_RATE' AND l.value:ship_confirmed_qty IS NOT NULL AND NOT IS_NULL_VALUE(l.value:ship_confirmed_qty);

  INSERT INTO CORE.INVENTORY_SNAPSHOT
    SELECT e.W, s.value:snapshot_id, s.value:item_id, s.value:facility_id, s.value:inventory_class, s.value:on_hand::NUMBER(38,6),
           s.value:quality_hold::NUMBER(38,6), s.value:allocated::NUMBER(38,6), s.value:in_transit::NUMBER(38,6), s.value:erp_book::NUMBER(38,6),
           NULL, s.value:visible_at::TIMESTAMP_TZ, s.index
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:snapshots) s WHERE e.C:metric_id = 'DAYS_INVENTORY';
  INSERT INTO CORE.DEMAND_EVENT
    SELECT e.W, e.W || '#' || d.index, d.value:item_id, d.value:facility_id, d.value:inventory_class, d.value:on::DATE, d.value:qty::NUMBER(38,6),
           'golden', d.value:visible_at::TIMESTAMP_TZ
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:demand) d WHERE e.C:metric_id = 'DAYS_INVENTORY';
  INSERT INTO CORE.WORLD_FACILITY
    WITH fac AS (
      SELECT e.W, s.value:facility_id::VARCHAR AS F FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:snapshots) s WHERE e.C:metric_id = 'DAYS_INVENTORY'
      UNION SELECT e.W, d.value:facility_id::VARCHAR FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:demand) d WHERE e.C:metric_id = 'DAYS_INVENTORY'
      UNION SELECT e.W, e.C:scope:facility_id::VARCHAR FROM CORE.EVAL_CASE e WHERE e.C:metric_id = 'DAYS_INVENTORY' AND e.C:scope:facility_id IS NOT NULL
    )
    SELECT fac.W, fac.F, COALESCE(NULLIF(e.C:timezone::VARCHAR, ''), e.C:facility_timezones[fac.F]::VARCHAR), NULL, NULL
    FROM fac JOIN CORE.EVAL_CASE e ON e.W = fac.W
    WHERE COALESCE(NULLIF(e.C:timezone::VARCHAR, ''), e.C:facility_timezones[fac.F]::VARCHAR) IS NOT NULL;

  INSERT INTO CORE.RECEIPT
    SELECT e.W, r.value:receipt_id, NULL, r.value:supplier_id, r.value:item_id, r.value:facility_id, r.value:accepted_qty::NUMBER(38,6),
           r.value:accepted_on::DATE, NULL, r.value:incoterm, r.value:origin_country, r.value:dest_country, r.value:calendar_id,
           r.value:visible_at::TIMESTAMP_TZ, r.index
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:receipts) r WHERE e.C:metric_id = 'LANDED_COST_PER_ACCEPTED_UNIT';
  INSERT INTO CORE.COST_COMPONENT
    SELECT e.W, r.value:receipt_id || '#' || c.index, r.value:receipt_id, c.value:kind, c.value:obligation_visible_at::TIMESTAMP_TZ,
           c.value:amount_minor::NUMBER(38,0), c.value:amount_visible_at::TIMESTAMP_TZ, c.value:currency, c.value:invoice_date::DATE,
           c.value:economic_date::DATE, c.value:fx_rate::NUMBER(38,12), c.value:fx_visible_at::TIMESTAMP_TZ,
           c.value:chargeable_weight::NUMBER(38,6), c.value:volume::NUMBER(38,6), c.value:allocation_pool_id, c.value:customs_value_minor::NUMBER(38,0),
           c.value:merchandise_value_minor::NUMBER(38,0), c.value:buyer_charged::BOOLEAN, 'golden', r.index * 1000 + c.index
    FROM CORE.EVAL_CASE e, LATERAL FLATTEN(e.C:receipts) r, LATERAL FLATTEN(r.value:components) c
    WHERE e.C:metric_id = 'LANDED_COST_PER_ACCEPTED_UNIT';

  RETURN OBJECT_CONSTRUCT('cases', (SELECT COUNT(*) FROM CORE.EVAL_CASE),
                          'po_lines', (SELECT COUNT(*) FROM CORE.PO_LINE WHERE WORLD_ID LIKE 'EVAL:%'),
                          'so_lines', (SELECT COUNT(*) FROM CORE.SO_LINE WHERE WORLD_ID LIKE 'EVAL:%'),
                          'receipts', (SELECT COUNT(*) FROM CORE.RECEIPT WHERE WORLD_ID LIKE 'EVAL:%'));
END;
$$;
