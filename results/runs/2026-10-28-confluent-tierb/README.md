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

## Load 2 (200 tx/s over worker connections, 30 min)

Pending.
