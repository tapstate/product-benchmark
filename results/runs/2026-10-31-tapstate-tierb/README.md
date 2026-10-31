# Tapstate Cloud, Tier B rerun, 2026-10-31

Rerun of `../2026-10-28-tapstate-tierb/` on a new dev cluster built after the fix for
https://github.com/tapstate/tapstate/issues/900. Same source schema `C##BENCH` (100,000 customers,
1,000,000 orders, 2,300,000 lines, counts verified before the start), same nest pipeline
(`vendors/tapstate/pipeline.json`), same target: Atlas M10, database `cr_tapstate`, collection
`BENCH_ORDERS`. Cluster: `tjdemo`, runtime 0.8.0, plan 2C8G, ap-southeast-1, created 2026-10-31.

## Attempt 1: failed while clearing the old target

The target collection still held about 814k documents from an earlier run. With
`on_full_load: clear` the sink empties it with one `deleteMany` before writing. That call outlasted
the MongoDB driver's socket read timeout and the pipeline went FAILED 100 s after start
(`connector.write-failed ... Timeout while receiving message`). The delete still finished on the
server, so the collection was empty afterwards. Evidence: `attempt1-*`. Reported upstream as
https://github.com/tapstate/tapstate/issues/939.

## Attempt 2: snapshot running, far below the needed rate

Stopped with state purged and started again at 09:39:24Z (RUNNING at 09:39:36Z).

| Stage | Rows | Rate | 2026-10-28 build |
|---|---|---|---|
| BENCH_CUSTOMERS | 100,000 in about 26 min (09:39:30Z to about 10:05Z) | about 64 rows/s | 12 to 15 rows/s |
| BENCH_LINES | 17,499 at 10:07:33Z, 58,459 at 10:26:58Z | about 35 rows/s | not reached |
| BENCH_ORDERS | pending | | not reached |
| Documents in Atlas | 0 so far: roots are written only when orders are read | | 0 |

During the lines stage about half of the line state reads backfill from the cold layer, at about
32 ms each; backfill time alone is 45% of wall time (`pipeline-metrics-20261031T102924Z.json`). At
35 rows/s the remaining 2.24M lines need about 18 hours, before the 1M orders. The cold-layer alert
also flips between raised and cleared every 7 to 8 seconds. Reported upstream as
https://github.com/tapstate/tapstate/issues/942.

The snapshot watch (`watch-snapshot.log`, `*-watch-snapshot.json`) ended on its 15-minute stall rule
with 0 documents, as expected in this stage order. Progress is sampled from the pipeline's snapshot
API into `snapshot-progress.log` while the pipeline keeps running, to measure the total snapshot
time. The load phase (200 changes per second) and lag probes wait for the snapshot to finish.
