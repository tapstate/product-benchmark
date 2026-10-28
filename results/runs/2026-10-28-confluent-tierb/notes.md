# Tier B run notes (Confluent, M10 rerun)

- Load 2 (09:51:58Z to 10:22:00Z): 352,496 transactions over 40 connections, 195.7 tx/s, 542,552 orders touched.
- Metrics API during load 2 (`metrics/load2-*.json`): source connector about 53 k change records/min
  (about 880/s, roughly 4.4 rows per transaction), Flink pending records near zero throughout (the
  join keeps up), Atlas sink about 10.5 k records/min (about 175 writes/s) with `tasks.max=1`, so the
  `order_doc` consumer backlog grew linearly to about 350 k records by 10:20Z. The sink, not Atlas
  (M10 took 3,500 bulk writes/s from the benchmark host), is the end-to-end bottleneck at 200 tx/s
  with the default single sink task. A tuned variant (sink `tasks.max=6`, one per `order_doc`
  partition) is run as load 3 after the drain.
