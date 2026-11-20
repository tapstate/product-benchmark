# Tier B run notes (Confluent)

- 04:58:22Z seed start, 04:59:29Z seed end (100k customers / 1M orders / 2.3M lines, schema C##TAPDATA).
- 04:59:58Z source connector `bench-oracle-cdc` created with `tasks.max=2`; RUNNING at 05:01:27Z.
- 05:01:27Z Flink insert statements submitted; 05:02:10Z Atlas sink created; snapshot watch started 05:02:14Z.
- 06:03Z status check: 771,395 docs in Atlas. Connector DEGRADED: task 0 RUNNING (snapshot), task 1
  USER_ACTIONABLE_ERROR "redo log consumer(s) failed to subscribe to the redo log topic 'bench-redo-log'".
  Cause: with `tasks.max > 1` the redo-log consumer task starts immediately, but the redo-log topic is only
  auto-created when task 0 begins mining after the snapshot. Tier A ran with `tasks.max=1` and never hit this.
- 06:03:51Z created topic `bench-redo-log` (1 partition) by hand. Task 1 did not self-recover after 90 s.
  Plan: let the snapshot finish, then pause/resume the connector to restart task 1 before the CDC load phase.
  Pitfall 11 for the prerequisites log: pre-create the redo-log topic whenever `tasks.max > 1`.

## Snapshot stage timing (Confluent Metrics API, 1-minute buckets)

| Stage | First record | Last record | Records | Note |
|---|---|---|---|---|
| Oracle CDC source, 3 tables | 05:01Z | 05:04Z | 3,400,000 | peak 1.62 M rows/min; snapshot of 3.4 M rows done in about 4 min |
| Flink `order_doc` output | 05:02Z | 05:19Z | 3,040,336 | 3.04 changelog records per final document: the parent-first join emits an order, then re-emits it as its customer and lines arrive |
| Atlas sink (1 task) | 05:02Z | still draining at 06:28Z | 1,730,507 by 06:28Z | steady 19.9 k records/min (about 330 writes/s): the end-to-end bottleneck |

- 06:24:10Z the document count reached 1,000,000, but only 822 k of 2.3 M nested lines were present
  (parent-first emission). The `watch` command gained `--lines-target` so completion means the
  nested line total is reached as well; `watch --label snapshot-lines` restarted at 06:28Z.
- The sink backlog (1.35 M records at 06:27Z) drains at the sink's write rate; projected completion about 07:35Z.
- Default configuration kept on purpose (sink `tasks.max=1`, as in Tier A). `order_doc` has 6
  partitions, so the sink could run up to 6 tasks; a tuned variant is a separate run if time allows.

## Target ceiling: the Atlas cluster is a shared tier

- `getParameter` answers "not allowed in this atlas tier"; connection limit 500; sample dataset present.
  Write probes from the benchmark host (same region, 1 ms ping): single `replaceOne` 6 to 9 ms, with
  periodic 1-second stalls (shared-tier throttling); `bulk_write` of 500 `ReplaceOne` sustained about
  430 ops/s. The Confluent sink's steady 330 writes/s therefore sits at the target's ceiling, not the
  sink's. Both vendors write to the same cluster, so Tier B compares them on equal footing, but the
  absolute snapshot throughput measures the target as much as the pipeline. A dedicated (M10 or larger)
  cluster is required before quoting Tier B numbers as vendor throughput.
- Write amplification still differs by vendor: Confluent's parent-first changelog wrote 3.04 records per
  final document (3.04 M sink writes for 1 M documents); a pipeline that assembles the document before
  writing needs about 1 M.

## Outcome

Run abandoned at 07:02Z. The owner upgraded the Atlas cluster to a dedicated M10 and Tier B was rerun from scratch
(`results/runs/2026-10-28-confluent-tierb`). The timings above are kept as evidence of the shared-tier ceiling only.
M10 write probe from the benchmark host: single `replaceOne` p50 4.2 ms / p99 7.9 ms, no stalls; `bulk_write` of 500 sustained about 3,500 ops/s (8x the shared tier).
