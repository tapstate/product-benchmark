-- Confluent Cloud for Apache Flink. The three source tables are created by the connector
-- topics (bench.BENCH.BENCH_CUSTOMERS etc.); they are read as changelog tables.
-- Adjust the inferred table definitions if the topic value format is not already a
-- *-debezium-registry format (see vendors/confluent/README.md).

CREATE TABLE order_doc (
  ORDER_ID    INT,
  CUSTOMER_ID INT,
  STATUS      STRING,
  ORDER_TS    TIMESTAMP(3),
  customer    ROW<CUSTOMER_ID INT, NAME STRING, TIER STRING, CREATED TIMESTAMP(3)>,
  lines       ARRAY<ROW<LINE_NO INT, SKU STRING, QTY INT, PRICE DECIMAL(18, 4)>>,
  PRIMARY KEY (ORDER_ID) NOT ENFORCED
) WITH (
  'changelog.mode' = 'upsert',
  'key.format'     = 'avro-registry',
  'value.format'   = 'avro-registry'
);

INSERT INTO order_doc
SELECT
  o.ORDER_ID,
  o.CUSTOMER_ID,
  o.STATUS,
  o.ORDER_TS,
  CASE WHEN c.CUSTOMER_ID IS NULL THEN CAST(NULL AS ROW<CUSTOMER_ID INT, NAME STRING, TIER STRING, CREATED TIMESTAMP(3)>)
       ELSE ROW(c.CUSTOMER_ID, c.NAME, c.TIER, c.CREATED) END AS customer,
  COALESCE(l.lines, CAST(ARRAY[] AS ARRAY<ROW<LINE_NO INT, SKU STRING, QTY INT, PRICE DECIMAL(18, 4)>>)) AS lines
FROM `bench.BENCH.BENCH_ORDERS` o
LEFT JOIN `bench.BENCH.BENCH_CUSTOMERS` c ON c.CUSTOMER_ID = o.CUSTOMER_ID
LEFT JOIN (
  SELECT ORDER_ID, ARRAY_AGG(ROW(LINE_NO, SKU, QTY, PRICE)) AS lines
  FROM `bench.BENCH.BENCH_LINES`
  GROUP BY ORDER_ID
) l ON l.ORDER_ID = o.ORDER_ID;
