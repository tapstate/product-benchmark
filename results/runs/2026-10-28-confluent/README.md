# Confluent Cloud, Tier A, 2026-10-28

Route: Oracle CDC Source Premium (LogMiner) -> three Avro topics -> four Flink SQL statements
(three `FROM_CHANGELOG` conversions, one join + `ARRAY_AGG` into an upsert table) -> MongoDB Atlas
Sink. Source: shared Oracle 19.17 EE (CDB$ROOT, DBA-role application user). Target: Atlas 8.0,
database `cr_confluent`, collection `orders`. Cluster: Standard, aws ap-east-1; Flink pool 10 CFU.

## Table 1. Correctness per phase

| Phase | Docs expected | Docs in target | Missing | Extra | Field diffs | Time to correct target | Result |
|---|---|---|---|---|---|---|---|
| Snapshot | 200 | 200 | 0 | 0 | 0 | 2 min 15 s from sink RUNNING to full collection (snapshot already in topics) | PASS |
| CDC round 1 (35 touched) | 35 | 35 | 0 | 0 | 0 | 74 s after commit | PASS |
| CDC round 2 (35 touched) | 35 | 35 | 0 | 0 | 0 | 38 s | PASS |
| CDC round 3 (35 touched) | 35 | 35 | 0 | 0 | 0 | 61 s | PASS |
| Source connector pause, round 4 committed while paused, resume | 36 | 36 | 0 | 0 | 0 | 67 s after resume | PASS |
| Flink statement stop, round 5 committed while stopped, resume | 35 | 35 | 0 | 0 | 0 | 49 s after resume | PASS |
| Order delete (order 3 with its lines) | 207 | 207 | 0 | 0 | 0 | 38 s | PASS |
| Final full reconcile (207 orders, 473 lines, 40 customers) | 207 | 207 | 0 | 0 | 0 | | PASS |
| Lag probes (3), commit to correct document | | | | | | p50 41.3 s, max 53.4 s | |

Not run: Oracle instance reboot (shared database). Transient states: the first reconcile after
each round saw stale STATUS, stale customer TIER and a missing new order for about 60 s, then
converged; no wrong final state was observed.

Timeline: Oracle prerequisites started 03:28:14Z; Confluent setup started 03:49:01Z; source
connector created 03:52:18Z, RUNNING 03:57:27Z; first fully correct collection 04:20:16Z.
Setup clock, empty org to first correct collection: 31 min, of which about 20 min were spent
on the ten pitfalls listed in `oracle-prereqs-log.md` (two connector recreations, one output
table rebuild). A second run with the published configuration would be about 12 min, dominated
by the two connector provisioning waits of about 5 min each.

Files: `*-seed.json`, `*-mutate-round*.json`, `*-reconcile-*.json`, `*-lag.json` (harness output),
`oracle-prereqs-log.md` (setup log, pitfalls), and the vendor configuration in
`../../../vendors/confluent/` (secrets redacted).
