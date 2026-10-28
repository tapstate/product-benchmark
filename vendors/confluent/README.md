# Confluent Cloud

Route: Oracle XStream CDC Source Premium (fallback: Oracle CDC Source Premium, LogMiner based)
to three topics, a Flink SQL statement that joins and aggregates them into an upsert table with a
nested schema, and the MongoDB Atlas Sink connector writing that table as documents.

Files:

| File | Purpose |
|---|---|
| `oracle-prereqs-rds.sql` | Oracle-side setup for the XStream connector on Amazon RDS for Oracle (run as the master user, then as the XStream admin) |
| `source-connector.json` | Oracle XStream CDC Source configuration, secrets redacted |
| `flink.sql` | the Flink SQL statements that build the nested document table |
| `atlas-sink.json` | MongoDB Atlas Sink configuration |

Setup order and what to record:

1. Oracle prerequisites (`oracle-prereqs-rds.sql`). Record the DBA step count and time.
2. Confluent Cloud environment, Basic cluster in the same cloud region as Oracle and Atlas,
   Schema Registry, Flink compute pool.
3. Source connector. Record whether the premium connector can be created on the account without
   a sales contact, and its displayed price.
4. Flink statements (`flink.sql`). Record CFU usage and any function or syntax limits hit.
5. Atlas sink. Record the first correct document time (`bench lag`).

Known properties to verify during the run (from Confluent's documentation at the time of writing):

- `ARRAY_AGG` has no `ORDER BY`, so line order inside the array is not guaranteed.
- `JSON_ARRAYAGG` and `JSON_OBJECTAGG` produce strings; use `ARRAY_AGG(ROW(...))` for real nested fields.
- CDC topics must be read with a `*-debezium-registry` value format with the connector set to
  after-state only, so that updates and deletes retract through the join and the aggregate.
- The XStream connector runs a single task.
- Deletes reach Atlas as tombstones on the upsert topic; the sink needs `delete.on.null.values=true`
  and a key-based document id strategy.
