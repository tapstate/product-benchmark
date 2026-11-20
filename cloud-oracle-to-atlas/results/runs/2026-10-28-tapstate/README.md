# Tapstate Cloud, Tier A, 2026-10-28

Route: one Oracle source (`bench-oracle`, schema `C##BENCH`, DBA-role application user), one
pipeline with a `nest` transform (orders root, lines array keyed by LINE_NO, customer object),
one Atlas destination (`bench-atlas`, database `cr_tapstate`). Build: Tapstate Cloud 0.8 preview,
cluster `tjdemoacc-preview-4` in aws ap-southeast-1 (Singapore), one runtime. Output collection
is named after the root table (`BENCH_ORDERS`); the pipeline definition is
`../../../vendors/tapstate/pipeline.json`.

## Table 1. Correctness per phase

| Phase | Docs expected | Docs in target | Missing | Extra | Field diffs | Time to correct target | Result |
|---|---|---|---|---|---|---|---|
| Snapshot | 200 | 200 | 0 | 0 | 0 | 70 s from start to correct collection (snapshot itself 460+200+40 rows in under 45 s) | PASS |
| CDC round 1 (35 touched) | 35 | 35 | 0 | 0 | 0 | 13 s after commit (first poll) | PASS |
| CDC round 2 (35 touched) | 35 | 35 | 0 | 0 | 0 | 13 s | PASS |
| CDC round 3 (35 touched) | 35 | 35 | 0 | 0 | 0 | 13 s | PASS |
| Pipeline pause, round 4 committed while paused, resume | 36 | 36 | 0 | 0 | 0 | 48 s after resume | PASS |
| Pipeline stop (state kept), round 5 committed while stopped, start | 34 | 34 | 0 | 0 | 0 | 60 s after start | PASS |
| Order delete (order 3 with its lines) | 207 | 207 | 0 | 0 | 0 | 14 s | PASS |
| Final full reconcile (207 orders, 473 lines, 40 customers) | 207 | 207 | 0 | 0 | 0 | | PASS |
| Lag probes (3), commit to correct document | | | | | | p50 2.3 s, max 3.2 s | |

Not run: Oracle instance reboot (shared database). The CDC-after-pause defect reported against
the 10-27 acceptance run (tapstate/tapstate#888) did not reproduce here: all three rounds were
applied without any pause.

Timeline: Oracle prerequisites (second schema, seed with supplemental logging) 04:35:50Z to
04:36:17Z; Tapstate setup started 04:36:30Z; connection tests 3.1 s (Oracle) and 0.8 s (Atlas);
first start 04:37:17Z failed after 50 s with `actuation.source-schema-not-discovered` (the start
was accepted and the pipeline reached FAILED, rather than being refused up front); schema
discovery 6.1 s; second start 04:39:33Z; first fully correct collection 04:40:40Z. Setup clock,
empty cluster to first correct collection: 4 min 10 s, including the one failed start.

Pitfalls: (1) a source must have its schema discovered before a pipeline over it can start, and
the start call does not say so until the pipeline has failed. Everything else worked first time
with the published pipeline definition.

Files: harness output as for the Confluent run, plus `connection-tests.json`.
