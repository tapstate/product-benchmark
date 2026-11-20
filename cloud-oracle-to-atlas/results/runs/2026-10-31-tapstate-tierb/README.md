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

## Attempt 2: stopped mid-snapshot, waiting for an upstream fix

Stopped with state purged and started again at 09:39:24Z (RUNNING at 09:39:36Z).

| Stage | Rows | Rate | 2026-10-28 build |
|---|---|---|---|
| BENCH_CUSTOMERS | 100,000 in about 26 min (09:39:30Z to about 10:05Z) | about 64 rows/s | 12 to 15 rows/s |
| BENCH_LINES | 17,499 at 10:07:33Z, 377,947 of 2,300,000 at 13:02:15Z | about 35 rows/s | not reached |
| BENCH_ORDERS | pending | | not reached |
| Documents in Atlas | 0 so far: roots are written only when orders are read | | 0 |

During the lines stage about half of the line state reads backfill from the cold layer, at about
32 ms each; backfill time alone is 45% of wall time (`pipeline-metrics-20261031T102924Z.json`). At
35 rows/s the remaining 2.24M lines need about 18 hours, before the 1M orders. The cold-layer alert
also flips between raised and cleared every 7 to 8 seconds. Reported upstream as
https://github.com/tapstate/tapstate/issues/942.

The snapshot watch (`watch-snapshot.log`, `*-watch-snapshot.json`) ended on its 15-minute stall rule
with 0 documents, as expected in this stage order. Progress was then sampled from the pipeline's
snapshot API into `snapshot-progress.log`.

### Where the time goes

- The nest stage is saturated. Its processing timer shows 100% of wall time busy, while the source
  used 0.46 s and the sink 0.007 s in total (`pipeline-metrics-20261031T130450Z.json`).
- Each state read is one cache transaction of about 17 sequential round trips to Atlas: admission
  checks, three workload-claim reads, a `listIndexes` structure check per collection touched, and
  then the read itself. Each op takes 0 ms on the server; the steps are 1 to 3 ms apart, about 37 ms
  per read (`cache-op-trace.json`, an Atlas profiler trace of about 1 s, grouped by session and
  transaction number).
- The nest vertex runs at parallelism 1, so reads are paid one key at a time.
- Not the cause: host CPU (a 2 vCPU burstable instance at about 31%, credits never exhausted), Atlas
  server time, connection churn (0.22 new connections/s), or the Oracle source.

Details and fix options are on https://github.com/tapstate/tapstate/issues/942.

### Stopped

Stopped at 13:05Z without purging state, so the cluster keeps the cache for inspection. Final status,
metrics and logs: `pipeline-*-20261031T130450Z.json`. The load phase and lag probes were not run.
The rerun waits for a build that fixes the per-read cost; it will start from a purged state and an
empty target.
