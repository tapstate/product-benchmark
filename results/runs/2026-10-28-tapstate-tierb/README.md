# Tapstate Cloud, Tier B, 2026-10-28

Same pipeline as the Tier A run (`../2026-10-28-tapstate/`): one nest pipeline (`BENCH_ORDERS` root,
`BENCH_LINES` embedded as the `lines` array, `BENCH_CUSTOMERS` embedded as the `customer` object),
`snapshot_and_cdc`, upsert sync into Atlas. Source schema `C##BENCH` seeded with 100,000 customers,
1,000,000 orders and 2,300,000 order lines (66 s). Target: Atlas 8.0 dedicated M10, database
`cr_tapstate`, collection `BENCH_ORDERS`. Cluster: preview, 0.8 build, ap-southeast-1.

## Snapshot: did not complete

| Measure | Value |
|---|---|
| Source discovery | 6.2 s |
| Pipeline put + start | start accepted 11:46:08Z, RUNNING at 11:46:50Z (42 s) |
| Rows read from Oracle (`records.in`) | 16,384 at 11:52Z, 24,576 at 11:58Z (reads wait on the transform) |
| Documents in Atlas | 0 at 11:58Z, 12 min after start |
| Nest transform throughput | 12 to 15 customer lookups per second (`nestStateAccesses...customer.refs`) |
| Cost per lookup | about 36 ms, all of it a cold-store backfill (`nestStateBackfillMillis / nestStateBackfills` for `customer.refs`) |
| Stored `customer.refs` entries | 0 throughout: every lookup misses and backfills again |
| Projection at this rate | about 22 hours for 1,000,000 orders |

Pipeline metrics sampled at 11:52Z, 11:55Z and 11:58Z are in `pipeline-metrics-*.json`; the
pipeline log is in `pipeline-logs-*.json`. The same pipeline completed the Tier A snapshot
(200 orders, 40 customers) in 70 s, where this per-key cost is invisible.

Reported upstream as https://github.com/tapstate/tapstate/issues/900. The Tier B load phase was not run for Tapstate because the snapshot never produced a
target to load against; it is to be rerun on a build with the fix.
