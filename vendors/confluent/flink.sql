-- Confluent Cloud for Apache Flink, LogMiner-route (Oracle CDC Source Premium) topics.
-- The connector writes one flattened record per change with an op_type field (R/I/U/D) and no
-- tombstones, so each topic is first turned into an upsert changelog with FROM_CHANGELOG.
-- Topics: bench.BENCH_CUSTOMERS, bench.BENCH_ORDERS, bench.BENCH_LINES (Avro; key = PK struct,
-- see key.template in source-connector.json). Oracle NUMBER(10) arrives as DECIMAL(10,0) and
-- TIMESTAMP(6) as TIMESTAMP_LTZ(3); the current-state tables keep those types on purpose:
-- casting a key column before an upsert sink makes the planner reject the statement.

CREATE TABLE customers_cur (CUSTOMER_ID DECIMAL(10,0), NAME STRING, TIER STRING, CREATED TIMESTAMP_LTZ(3),
  PRIMARY KEY (CUSTOMER_ID) NOT ENFORCED) WITH ('changelog.mode' = 'upsert');
CREATE TABLE orders_cur (ORDER_ID DECIMAL(10,0), CUSTOMER_ID DECIMAL(10,0), STATUS STRING, ORDER_TS TIMESTAMP_LTZ(3),
  PRIMARY KEY (ORDER_ID) NOT ENFORCED) WITH ('changelog.mode' = 'upsert');
CREATE TABLE lines_cur (ORDER_ID DECIMAL(10,0), LINE_NO DECIMAL(10,0), SKU STRING, QTY DECIMAL(10,0), PRICE DECIMAL(18,4),
  PRIMARY KEY (ORDER_ID, LINE_NO) NOT ENFORCED) WITH ('changelog.mode' = 'upsert');

-- Two insert codes (R = snapshot read, I = insert) must share one mapping key.
INSERT INTO customers_cur SELECT CUSTOMER_ID, NAME, TIER, CREATED
FROM FROM_CHANGELOG(input => TABLE `bench.BENCH_CUSTOMERS` PARTITION BY CUSTOMER_ID,
  op => DESCRIPTOR(op_type), op_mapping => MAP['R, I','INSERT', 'U','UPDATE_AFTER', 'D','DELETE']);
INSERT INTO orders_cur SELECT ORDER_ID, CUSTOMER_ID, STATUS, ORDER_TS
FROM FROM_CHANGELOG(input => TABLE `bench.BENCH_ORDERS` PARTITION BY ORDER_ID,
  op => DESCRIPTOR(op_type), op_mapping => MAP['R, I','INSERT', 'U','UPDATE_AFTER', 'D','DELETE']);
INSERT INTO lines_cur SELECT ORDER_ID, LINE_NO, SKU, QTY, PRICE
FROM FROM_CHANGELOG(input => TABLE `bench.BENCH_LINES` PARTITION BY (ORDER_ID, LINE_NO),
  op => DESCRIPTOR(op_type), op_mapping => MAP['R, I','INSERT', 'U','UPDATE_AFTER', 'D','DELETE']);

-- The nested order document. An empty ARRAY[] literal is not accepted, so an order without
-- lines carries NULL; the referee treats null, [] and an absent field alike.
-- TIMESTAMP_LTZ, not TIMESTAMP: Flink writes TIMESTAMP as Avro local-timestamp-millis, which the
-- Atlas sink stores as a plain integer; TIMESTAMP_LTZ becomes timestamp-millis and lands as a BSON date.
-- value.fields-include = all: otherwise the key column ORDER_ID is absent from the document body.
CREATE TABLE order_doc (
  ORDER_ID INT, CUSTOMER_ID INT, STATUS STRING, ORDER_TS TIMESTAMP_LTZ(3),
  customer ROW<CUSTOMER_ID INT, NAME STRING, TIER STRING, CREATED TIMESTAMP_LTZ(3)>,
  lines ARRAY<ROW<LINE_NO INT, SKU STRING, QTY INT, PRICE DECIMAL(18, 4)>>,
  PRIMARY KEY (ORDER_ID) NOT ENFORCED
) WITH ('changelog.mode' = 'upsert', 'key.format' = 'avro-registry', 'value.format' = 'avro-registry',
        'value.fields-include' = 'all');

INSERT INTO order_doc
SELECT CAST(o.ORDER_ID AS INT), CAST(o.CUSTOMER_ID AS INT), o.STATUS, o.ORDER_TS,
  CASE WHEN c.CUSTOMER_ID IS NULL THEN CAST(NULL AS ROW<CUSTOMER_ID INT, NAME STRING, TIER STRING, CREATED TIMESTAMP_LTZ(3)>)
       ELSE ROW(CAST(c.CUSTOMER_ID AS INT), c.NAME, c.TIER, c.CREATED) END,
  l.lines
FROM orders_cur o
LEFT JOIN customers_cur c ON c.CUSTOMER_ID = o.CUSTOMER_ID
LEFT JOIN (SELECT ORDER_ID, ARRAY_AGG(ROW(CAST(LINE_NO AS INT), SKU, CAST(QTY AS INT), PRICE)) AS lines
           FROM lines_cur GROUP BY ORDER_ID) l ON l.ORDER_ID = o.ORDER_ID;
