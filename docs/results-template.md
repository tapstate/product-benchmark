# Results template

Copy these tables into the review. Every numeric cell points at a file under `results/runs/`.

## Table 1. Correctness per phase (one per product)

| Phase | Docs expected | Docs in target | Missing | Extra | Field diffs | Lag p50 / max (s) | Result |
|---|---|---|---|---|---|---|---|
| Snapshot | 200 | | | | | n/a | |
| CDC round 1 | 201 | | | | | | |
| CDC round 2 | 202 | | | | | | |
| CDC round 3 | 203 | | | | | | |
| Pause / resume | 203 | | | | | | |
| Connector restart | 203 | | | | | | |
| Oracle restart | 203 | | | | | | |
| Order delete | 202 | | | | | | |

Field diffs are classified under the table: value, type (for example a date stored as an
integer), absent, nested (stale embedded customer, wrong array membership).

## Table 2. Feature matrix (Yes / No / Partial with a one-line note)

| Capability | Product A | Product B | Product C |
|---|---|---|---|
| CDC mechanism (redo log, XStream, polling) | | | |
| Deletes propagated to the target | | | |
| Nested array from a child table | | | |
| Nested object from a parent table | | | |
| Fan-out on parent update | | | |
| Ordering guarantee inside arrays | | | |
| Initial load consistent with the CDC start point | | | |
| Schema change handling | | | |
| Restart without loss or duplicates | | | |
| Monitoring and lag visibility | | | |
| API or infrastructure-as-code for the whole pipeline | | | |
| Components required end to end | | | |

## Table 3. User experience (measured during setup)

| Metric | Product A | Product B | Product C |
|---|---|---|---|
| Empty account to first correct document (wall clock) | | | |
| UI steps / configuration artifacts | | | |
| DBA prerequisites on Oracle (grants, logging, parameters) | | | |
| Sales contact required for any component | | | |
| Errors hit during setup and how they surfaced | | | |
| Documentation gaps | | | |
| Code written (SQL, JSON, scripts), lines | | | |

## Table 4. Pricing

| Cost line | Product A | Product B | Product C |
|---|---|---|---|
| List price per component (source, processing, sink, platform) | | | |
| Minimum always-on monthly cost for this workload | | | |
| Measured bill for the test window, normalised to 30 days | | | |
| Pricing model (per row, per task-hour, per compute unit, per active row) | | | |
| Trial availability | | | |

## Table 5. Tier B load

| Metric | Product A | Product B | Product C |
|---|---|---|---|
| Snapshot: rows per second, time to consistent target | | | |
| Lag under 200 tx/s: p50 / p95 / max | | | |
| Backlog drain after load stops | | | |
| Touched-order reconcile after load | | | |

## Table 6. Scorecard (1 to 5, each cell cites the table above that justifies it)

| Dimension | Product A | Product B | Product C |
|---|---|---|---|
| Correctness (Table 1) | | | |
| Features (Table 2) | | | |
| Setup experience (Table 3) | | | |
| Operations (Table 1, restart rows) | | | |
| Price for this workload (Table 4) | | | |
| Scale (Table 5) | | | |
