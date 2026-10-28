# Oracle prerequisites log (shared source, Oracle 19.17 EE, CDB$ROOT)

| Step | By | Started (UTC) | Result |
|---|---|---|---|
| Seed BENCH_* (Tier A) with ALL COLUMNS supplemental logging | DBA-role user | 2026-10-28T03:28:14Z | PASS, 1.5 s |
| Create C##CFLTADMIN, C##CFLTUSER and system grants | DBA-role user | 2026-10-28T03:28:56Z | partial: CREATE SESSION, SET CONTAINER, SELECT/LOCK/FLASHBACK ANY TABLE, LOGMINING, SELECT ANY TRANSACTION, SELECT ANY DICTIONARY, CREATE TABLE, CREATE SEQUENCE granted |
| SELECT_CATALOG_ROLE, EXECUTE_CATALOG_ROLE | DBA-role user | same | FAIL: ORA-01924 / ORA-01932 (no ADMIN OPTION) |
| EXECUTE ON SYS.DBMS_LOGMNR, DBMS_LOGMNR_D | DBA-role user | same | FAIL: ORA-01031 insufficient privileges |
| DBMS_XSTREAM_AUTH.GRANT_ADMIN_PRIVILEGE | DBA-role user | same | FAIL: PLS-00201 package not visible to a non-SYS user |
| Remaining steps (`oracle-prereqs-sys.sql`) | SYSDBA | 2026-10-28T03:45Z | BLOCKED: no SYS or SYSTEM password available (ORA-01017 with the application user's password) |
| LogMiner-route check with the existing DBA-role user (C##TAPDATA) | benchmark | 2026-10-28T03:50Z | PASS: all listed system privileges, EXECUTE on DBMS_LOGMNR and DBMS_LOGMNR_D, DBMS_LOGMNR_D.BUILD succeeded |

Decision: the Confluent leg runs the LogMiner-based Oracle CDC Source Premium connector with the same DBA-role user the other products use. The XStream connector is deferred until SYS access exists.

Finding: both Confluent Oracle CDC connectors' documented setup needs SYS-level steps on a multitenant 19c; a DBA-role
application user is not enough. The product under test from the same database vendor (Tapstate) ran
its connection test with the DBA-role user alone.

## Confluent Cloud setup log

| Step | Started (UTC) | Result |
|---|---|---|
| CLI login, existing org with FREETRIAL400 ($400, expires 2026-11-27), payment linked to AWS Marketplace, no card | 2026-10-28T03:49:01Z | OK |
| Existing Standard cluster `cluster_0` in aws ap-east-1 (Hong Kong), Schema Registry Essentials, one 10-CFU Flink pool | pre-existing | reused |
| Cloud API key and Kafka API key | 2026-10-28T03:49Z | OK |
| Oracle CDC Source Premium connector created via CLI (`OracleCdcSource`, tasks.max=1, Avro, topics `bench.<table>`) | 2026-10-28T03:52:18Z | accepted on the trial account with no sales contact; provisioning |

Note: the default topic template `${databaseName}.${schemaName}.${tableName}` cannot be used with a
common-user schema such as `C##TAPDATA` because `#` is not a legal Kafka topic character; a custom
template is required.
| Connector RUNNING, snapshot of 700 rows visible in topics | 2026-10-28T03:57:27Z | 5 min 9 s after creation |
| Flink CREATE TABLE x4, INSERT x4 (first attempt) | 2026-10-28T04:02Z | 4 failures, see pitfalls |
| Atlas sink created | 2026-10-28T04:03Z | FAILED validation: delete.on.null.values needs a key-based id strategy; fixed with FullKeyStrategy, RUNNING |
| Source connector deleted and recreated with key.template=${primaryKeyStruct}; topics and schemas deleted | 2026-10-28T04:07Z | provisioning again |

Pitfalls recorded (each cost one failed statement and a documentation search):

1. `op_mapping` rejects two codes mapped to the same row kind (`'R','INSERT','I','INSERT'`); the syntax is `'R, I','INSERT'`.
2. A composite `PARTITION BY` must be parenthesised: `PARTITION BY (ORDER_ID, LINE_NO)`.
3. `ARRAY[]` (empty array literal) is rejected with "Require at least 1 argument".
4. Casting a key column (`CAST(ORDER_ID AS INT)`) between `FROM_CHANGELOG` and an upsert sink fails planning with "changelog mode mismatch"; the current-state tables must keep the source key types.
5. With a single-column primary key the connector's default `key.template` writes a bare Avro decimal as the record key, which Flink's inferred table cannot deserialize ("Error while deserializing key"). Fix: `key.template=${primaryKeyStruct}`, which required deleting the connector, the topics and the registered schemas and re-snapshotting.
6. The CLI's `schema-registry subject delete` does not exist in 4.81.0; schemas are removed with `schema delete --version all`, twice (soft, then `--permanent`).
7. Flink `TIMESTAMP(3)` is written to Avro as `local-timestamp-millis`; the Atlas sink stores that as a plain integer, not a BSON date (first reconcile: 200 type differences). `TIMESTAMP_LTZ(3)` becomes `timestamp-millis` and lands as a date.
8. An upsert table's key column is excluded from the record value by default, so the document had no top-level ORDER_ID; `'value.fields-include' = 'all'` is needed.
9. After the output topic was dropped and recreated, the paused sink resumed from a stale offset and wrote only 58 of 200 documents; the sink had to be deleted and recreated with `consumer.override.auto.offset.reset=earliest`.
10. The `_id` written by `FullKeyStrategy` is a sub-document `{ORDER_ID: n}`, not the scalar order id; the only way to get a scalar `_id` and still honour deletes would be a key with a single `_id` field (`ProvidedInKeyStrategy`), which the Flink table would have to be shaped for.

Observed: line order inside `lines` is arbitrary (for example LINE_NO 2, 3, 1, 4), as expected from `ARRAY_AGG` without `ORDER BY`. The output topic held 231 records for 200 orders after the snapshot: 31 intermediate join states were emitted and then overwritten.
