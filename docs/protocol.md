# Benchmark protocol

## Workflow under test

Sync three Oracle tables into one MongoDB Atlas collection where every document is one order
with its lines embedded as an array and its customer embedded as an object. Initial load, then
continuous change capture. This is the everyday "relational to document" job: the shape every
vendor documents, and the one where products differ most, because a change to a child row must
rewrite the parent document and a change to a parent row must fan out to every document that
embeds it.

## Source

| Table | Key | Columns |
|---|---|---|
| `BENCH_CUSTOMERS` | CUSTOMER_ID | NAME, TIER, CREATED (TIMESTAMP) |
| `BENCH_ORDERS` | ORDER_ID | CUSTOMER_ID, STATUS, ORDER_TS (TIMESTAMP) |
| `BENCH_LINES` | ORDER_ID, LINE_NO | SKU, QTY, PRICE (NUMBER(18,4)) |

Rows are deterministic functions of their ids (`bench/fixture.py`). Every 10th order has no
lines; every 25th order points at a customer that does not exist.

## Target document contract

```
{ _id: <ORDER_ID>, ORDER_ID, CUSTOMER_ID, STATUS, ORDER_TS,
  customer: { CUSTOMER_ID, NAME, TIER, CREATED } | null,
  lines:    [ { LINE_NO, SKU, QTY, PRICE }, ... ] }
```

Rules the referee applies (`bench/reconcile.py`):

- Field names are matched case-insensitively (`ORDER_ID`, `order_id` and `Order_Id` are the same field).
- Array order is not asserted; lines are compared as a set keyed by LINE_NO.
- Timestamps must be BSON dates; millisecond precision is accepted, an integer or a string is a
  type difference.
- Numbers compare by value (int, Decimal128, double are equivalent when equal).
- An order without lines may carry an empty array or omit the field. An order whose customer does
  not exist carries `null` or omits the field.
- Anything else that differs is reported with its order id, field and kind
  (`value`, `type`, `absent`, `nested`).

## Tiers

| Tier | Customers | Orders | Lines | Purpose |
|---|---|---|---|---|
| A | 40 | 200 | 460 | Correctness: every phase reconciled row by row |
| B | 100,000 | 1,000,000 | 2,300,000 | Throughput, lag under load, cost at volume |
| C | 1,000,000 | 10,000,000 | 23,000,000 | Snapshot throughput only, optional |

## Phases (identical for every product)

| # | Phase | What happens | Measured |
|---|---|---|---|
| 0 | Setup | Empty vendor account to a running pipeline | wall clock, steps, config artifacts, DBA prerequisites, errors, documentation gaps |
| 1 | Snapshot | Initial load of the seeded tables | time to a fully consistent target; full reconcile (Tier A) or counts plus sampled reconcile (Tier B) |
| 2 | CDC rounds 1 to 3 | `bench mutate N`: insert an order with 3 lines, ship about 28 orders, delete one line, upgrade one customer's tier (fan-out) | reconcile of touched orders; lag probes |
| 3 | Operations | Pause and resume the pipeline; restart the source connector or job; reboot the Oracle instance | reconcile after each; loss or duplicates |
| 4 | Delete | `bench delete-order`: delete a whole order with its lines | document removed |
| 5 | Load (Tier B) | `bench load --rate 200 --seconds 1800` while `bench lag` probes run every 30 s | lag p50 / p95 / max, backlog drain time, reconcile of touched orders |
| 6 | Billing | 24 h always-on, then export the vendor bill | measured cost, normalised to 30 days |

Phase 2 of the review adds a two-level document (customer with orders with lines) once every
product has results on the one-level document.

## Fairness rules

- Same Oracle instance, same seed, same change script, same referee, same Atlas cluster.
- Each product is configured along its own documented happy path. No undocumented tuning.
- Every limit found is stated against the vendor's documentation of the day, with a link.
- All configuration used is published with the results, secrets redacted.
- A vendor's correction of a published finding is appended, not silently merged.

## Evidence

Every run folder under `results/runs/<date>-<vendor>/` holds the JSON produced by `bench`
(seed, mutate, load, lag, reconcile), the vendor configuration (SQL, connector JSON, pipeline
definitions, screenshots), timestamps, and the billing export. A number without a run folder is
not published.
