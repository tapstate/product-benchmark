# Confluent Cloud, Tier B, 2026-10-28

Same route and configuration as the Tier A run (`../2026-10-28-confluent/`), with the source connector
at `tasks.max=2` and the redo-log topic pre-created (see pitfall 11 below). Source schema `C##TAPDATA`
seeded with 100,000 customers, 1,000,000 orders and 2,300,000 order lines (66 s). Target: Atlas 8.0
dedicated M10 (same region as the benchmark host), database `cr_confluent`, collection `orders`.
A first attempt on the project's shared-tier Atlas cluster was abandoned because the target
throttled writes at about 330 per second; it is archived in `../2026-10-28-confluent-tierb-shared/`.

## Snapshot

| Measure | Value |
|---|---|
| Setup start (redo-log topic, connector create) | 08:11:02Z |
| Source connector RUNNING (both tasks) | 08:15:53Z |
| Flink tables and inserts submitted | 08:16:02Z to 08:17:50Z |
| Atlas sink created, watch started | 08:17:51Z |
| First documents in Atlas | about 08:23Z |
| 1,000,000 documents present | 08:55Z (t = 2,270 s), with 1.81 M of 2.3 M lines |
| All 1,000,000 documents with all 2,300,000 lines | 09:15:55Z (t = 3,480 s) |
| End to end, setup start to complete collection | 64 min 53 s |
| Sink create to complete collection | 58 min 4 s; 287 docs/s and 661 lines/s averaged over the watch |
| Sampled reconcile (1 %, 9,970 orders) | missing 0, extra 0, field diffs 0: PASS |

Stage breakdown from the Confluent Metrics API (1-minute buckets): Oracle snapshot of 3.4 M rows
08:16 to 08:19 (peak 1.52 M rows/min); Flink `order_doc` output 08:24 to 08:31, 2.69 M changelog
records for 1 M final documents (the parent-first join emits an order, then re-emits it as its
customer and lines arrive); Atlas sink (1 task) 08:24 to 09:16, peak 3,700 records/s, average about
1,000 records/s, slower in the tail where most records replace an existing document.

Pitfall 11: with `tasks.max > 1` the redo-log consumer task starts immediately and fails with
`USER_ACTIONABLE_ERROR` if the redo-log topic does not exist yet, because the topic is only
auto-created when mining begins after the snapshot. Pre-create the topic. Pitfall 12: the document
count reaching the row count does not mean the snapshot is complete on this route; at that moment
only 79 % of the nested lines were present. Watch the nested line total (harness `watch --lines-target`).

## Load 1 (single connection, 30 min)

The first load run used the harness's original single-connection generator, which the 50 ms round
trip to Oracle limits to about 7 transactions per second (about four round trips per transaction).
It is kept as the low-rate data point; load 2 below is the 200 tx/s run with the multi-connection
generator that replaced it.

| Measure | Value |
|---|---|
| Window | 09:17:11Z to 09:47:12Z |
| Transactions / achieved rate | 12,707 / 7.1 tx/s (requested 200) |
| Orders touched | 22,772 |
| Reconcile after load (1,000 most recently touched orders + 1 % sample, 10,964 orders) | missing 0, extra 0, field diffs 0: PASS at 09:51:28Z, 4 min 16 s after the load ended (upper bound on the drain) |
| Lag probes during the load | see the lag section below |

## Load 2 (200 tx/s over worker connections, 30 min, default sink with 1 task)

| Measure | Value |
|---|---|
| Window | 09:51:58Z to 10:22:00Z |
| Transactions / achieved rate | 352,496 / 195.7 tx/s over 40 connections |
| Orders touched | 542,552 |
| Source connector output | about 53 k change records/min (880/s), steady |
| Flink pending records | near zero throughout: the join keeps up |
| Atlas sink throughput | about 10.5 k records/min (175 writes/s) with `tasks.max=1` |
| Sink backlog (`order_doc` consumer lag) | grows linearly during the load, peak 376 k records at 10:22Z |
| Backlog drain after the load stopped | 38 min 30 s (backlog 1 record at 11:00Z) |
| Reconcile after load (1,000 most recently touched + 1 % sample, 10,959 orders) | FAIL with 226 missing and 2,668 field diffs at 10:23Z, converging each minute; PASS at 11:00:32Z, 38 min 32 s after the load ended |

The pipeline does not keep up with 200 tx/s in its default configuration: the single sink task is
the bottleneck, not Atlas (the M10 cluster took 3,500 bulk writes/s from the benchmark host) and not
Flink. Every document reached the correct state once the backlog drained; no wrong final state.
Metrics are in `metrics/load2-*.json` and `metrics/drain2-*.json` (Confluent Metrics API, 1-minute buckets).

## Load 3 (200 tx/s, sink raised to 6 tasks, one per `order_doc` partition)

The only change from load 2 is `tasks.max=6` on the Atlas sink (connector update accepted at
11:12:09Z, six tasks RUNNING 21 s later; the update is an in-place rolling restart, no data loss).

| Measure | Value |
|---|---|
| Window | 11:12:30Z to 11:42:32Z |
| Transactions / achieved rate | 351,809 / 195.3 tx/s over 40 connections |
| Orders touched | 585,615 |
| Source connector output | about 53 k change records/min, steady |
| Atlas sink throughput | 17 k to 33 k records/min (280 to 550 writes/s), tracking the join output |
| Sink backlog | bounded, between 3 k and 52 k records during the load |
| Backlog drain after the load stopped | about 2 min (backlog 6 records at 11:44Z) |
| Reconcile after load (1,000 most recently touched + 1 % sample, 10,961 orders) | FAIL at 11:43:38Z (101 missing, 192 field diffs), PASS at 11:45:14Z, 2 min 42 s after the load ended |

With six sink tasks the route sustains 200 tx/s end to end. Metrics in `metrics/load3-*.json`.

## Lag probes (one probe order every 30 s plus its own latency, 60 probes, 09:17Z to 11:51Z)

One probe run spanned all three loads; the samples are split by the probe's commit time
(encoded in its order id). A probe counts as a timeout after 600 s.

| Window | Probes | p50 | p95 | max | Timeouts |
|---|---|---|---|---|---|
| Load 1, 7 tx/s | 20 | 61.1 s | 68.8 s | 68.8 s | 0 |
| Load 2, 196 tx/s, 1 sink task | 3 | over 600 s | | | 2 of 3 (the third landed at 600.4 s) |
| Drain after load 2 | 5 | | | | 3 of 5 |
| Idle between loads (sink update window) | 8 | 60.7 s | 64.2 s | 64.2 s | 0 |
| Load 3, 195 tx/s, 6 sink tasks | 14 | 87.1 s | 246.1 s | 246.1 s | 0 |
| Idle after load 3 | 6 | 66.2 s | 68.7 s | 68.7 s | 0 |

The idle floor on this route is about 60 s at Tier B (41 s in Tier A). Under 200 tx/s with the
default sink the probes do not arrive within 10 minutes; with six sink tasks they arrive with a
median of 87 s and a tail of about four minutes. File: `*-lag.json` (all samples, with marker ids).
