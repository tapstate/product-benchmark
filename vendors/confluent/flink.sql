-- Confluent Cloud for Apache Flink, LogMiner-route (Oracle CDC Source Premium) topics.
-- The connector writes one flattened record per change with an op_type field (R/I/U/D) and no
-- tombstones, so each topic is first turned into an upsert changelog with FROM_CHANGELOG.
-- Topic names: bench.BENCH_CUSTOMERS, bench.BENCH_ORDERS, bench.BENCH_LINES (Avro, key = PK struct).

-- 1. Current-state tables (one per source table)
CREATE TABLE customers_cur (
  CUSTOMER_ID INT, NAME STRING, TIER STRING, CREATED TIMESTAMP(3),
  PRIMARY KEY (CUSTOMER_ID) NOT ENFORCED
) WITH ('changelog.mode' = 'upsert');

INSERT INTO customers_cur
SELECT CUSTOMER_ID, NAME, TIER, CREATED
FROM FROM_CHANGELOG(
  input => TABLE `bench.BENCH_CUSTOMERS` PARTITION BY CUSTOMER_ID,
  op => DESCRIPTOR(op_type),
  op_mapping => MAP['R','INSERT', 'I','INSERT', 'U','UPDATE_AFTER', 'D','DELETE']);

CREATE TABLE orders_cur (
  ORDER_ID INT, CUSTOMER_ID INT, STATUS STRING, ORDER_TS TIMESTAMP(3),
  PRIMARY KEY (ORDER_ID) NOT ENFORCED
) WITH ('changelog.mode' = 'upsert');

INSERT INTO orders_cur
SELECT ORDER_ID, CUSTOMER_ID, STATUS, ORDER_TS
FROM FROM_CHANGELOG(
  input => TABLE `bench.BENCH_ORDERS` PARTITION BY ORDER_ID,
  op => DESCRIPTOR(op_type),
  op_mapping => MAP['R','INSERT', 'I','INSERT', 'U','UPDATE_AFTER', 'D','DELETE']);

CREATE TABLE lines_cur (
  ORDER_ID INT, LINE_NO INT, SKU STRING, QTY INT, PRICE DECIMAL(18, 4),
  PRIMARY KEY (ORDER_ID, LINE_NO) NOT ENFORCED
) WITH ('changelog.mode' = 'upsert');

INSERT INTO lines_cur
SELECT ORDER_ID, LINE_NO, SKU, QTY, PRICE
FROM FROM_CHANGELOG(
  input => TABLE `bench.BENCH_LINES` PARTITION BY ORDER_ID, LINE_NO,
  op => DESCRIPTOR(op_type),
  op_mapping => MAP['R','INSERT', 'I','INSERT', 'U','UPDATE_AFTER', 'D','DELETE']);

-- 2. The nested order document
CREATE TABLE order_doc (
  ORDER_ID    INT,
  CUSTOMER_ID INT,
  STATUS      STRING,
  ORDER_TS    TIMESTAMP(3),
  customer    ROW<CUSTOMER_ID INT, NAME STRING, TIER STRING, CREATED TIMESTAMP(3)>,
  lines       ARRAY<ROW<LINE_NO INT, SKU STRING, QTY INT, PRICE DECIMAL(18, 4)>>,
  PRIMARY KEY (ORDER_ID) NOT ENFORCED
) WITH ('changelog.mode' = 'upsert', 'key.format' = 'avro-registry', 'value.format' = 'avro-registry');

INSERT INTO order_doc
SELECT
  o.ORDER_ID, o.CUSTOMER_ID, o.STATUS, o.ORDER_TS,
  CASE WHEN c.CUSTOMER_ID IS NULL THEN CAST(NULL AS ROW<CUSTOMER_ID INT, NAME STRING, TIER STRING, CREATED TIMESTAMP(3)>)
       ELSE ROW(c.CUSTOMER_ID, c.NAME, c.TIER, c.CREATED) END,
  COALESCE(l.lines, CAST(ARRAY[] AS ARRAY<ROW<LINE_NO INT, SKU STRING, QTY INT, PRICE DECIMAL(18, 4)>>))
FROM orders_cur o
LEFT JOIN customers_cur c ON c.CUSTOMER_ID = o.CUSTOMER_ID
LEFT JOIN (
  SELECT ORDER_ID, ARRAY_AGG(ROW(LINE_NO, SKU, QTY, PRICE)) AS lines
  FROM lines_cur GROUP BY ORDER_ID
) l ON l.ORDER_ID = o.ORDER_ID;
