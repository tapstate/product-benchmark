# product-benchmark

A reproducible, vendor-neutral benchmark for one everyday data-integration job: **sync Oracle
tables into MongoDB Atlas as nested documents**, initial load plus continuous change capture.
It is built to compare managed products (Tapstate Cloud, Confluent Cloud, Fivetran, and any
other) on the same source, the same changes and the same referee, so that anyone can rerun it
and check a published result.

The job: three tables, `BENCH_CUSTOMERS`, `BENCH_ORDERS`, `BENCH_LINES`, become one `orders`
collection where each document is an order with its lines embedded as an array and its customer
embedded as an object. Updates and deletes on any of the three tables must be reflected in the
documents.

What is here:

| Path | Contents |
|---|---|
| `docs/protocol.md` | the scenario, document contract, tiers, phases, fairness rules, evidence rules |
| `docs/results-template.md` | the tables a review fills in |
| `bench/` | the harness: seed, scripted change rounds, sustained load, lag probes, reconcile |
| `vendors/<name>/` | the configuration used for each product, with notes on what was needed |
| `infra/` | provisioning the shared Oracle 19c source |
| `results/runs/` | evidence folders, one per run |

## Quick start

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp bench.env.example bench.env && chmod 600 bench.env   # fill in Oracle and Atlas credentials
.venv/bin/python -m unittest discover -s tests -t .      # the referee's own tests, no database needed

# 1. Seed the source (Tier A: 40 customers, 200 orders, 460 lines)
.venv/bin/python -m bench --vendor <name> seed --supplemental-logging

# 2. Set up the product under test from vendors/<name>/README.md, pointing it at the
#    BENCH_* tables and at Atlas database cr_<name>, collection orders. Start the clock.
#    If the product picks its own collection name, pass --database/--collection to every
#    command below (Tapstate: --collection BENCH_ORDERS).

# 3. Snapshot phase
.venv/bin/python -m bench --vendor <name> reconcile --phase snapshot

# 4. Change rounds (repeat for rounds 2 and 3)
.venv/bin/python -m bench --vendor <name> mutate 1
.venv/bin/python -m bench --vendor <name> lag --samples 3
.venv/bin/python -m bench --vendor <name> reconcile --phase cdc1 --touched results/runs/*-<name>/*mutate-round1.json

# 5. Operations and delete phases: pause/resume, restart, reboot, then
.venv/bin/python -m bench --vendor <name> delete-order 3
.venv/bin/python -m bench --vendor <name> reconcile --phase final
```

Every command writes a JSON file under `results/runs/<date>-<vendor>/`. `reconcile` exits 1 on
any difference and prints the first ones, classified as value, type, absent or nested.

Tier B (1 M orders) uses `--tier b` on every command, `load --rate 200 --seconds 1800` for the
sustained change mix, and `reconcile --sample 0.01 --touched ...` instead of a full compare. The
full Tier B procedure is in "Run it yourself" below.

## Run it yourself

This section is for someone rerunning a published comparison, or adding a product, without
access to the original environment.

### What you need

| Item | Requirement | Why |
|---|---|---|
| Oracle | 19c or later, ARCHIVELOG on, a user that can read LogMiner views | log-based CDC products require it; `infra/` provisions one on Amazon RDS |
| MongoDB Atlas | M10 or larger for Tier B; a free or shared tier is enough for Tier A | the shared tier throttles writes at about 330 per second, which becomes the bottleneck at Tier B (`results/runs/2026-10-28-confluent-tierb-shared/`) |
| Product accounts | one per product under test | Tapstate Cloud is in an invite-only preview at the time of writing; ask the maintainers of this repository for access |
| Runner host | Python 3.12 (the version CI tests), network access to Oracle and Atlas | the harness itself does not need to sit near the products |

Put every product in the same cloud region as the Oracle source and the Atlas cluster, or record
the distances. Lag figures include the network path to the source: in the published runs the
source was in Shenzhen, Confluent ran in Hong Kong and Tapstate in Singapore.

### 1. Check the harness before any product

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp bench.env.example bench.env && chmod 600 bench.env
.venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python -m bench --vendor selfcheck seed --supplemental-logging
.venv/bin/python -m bench --vendor selfcheck perfect-sink
.venv/bin/python -m bench --vendor selfcheck reconcile --phase snapshot     # must PASS
```

If this does not pass, the problem is in the environment, not in a product.

### 2. Tier A (200 orders): correctness

Follow the quick start above, phase by phase, with the product's `vendors/<name>/README.md`.
Record every failed attempt and the wall-clock time of setup; the reviews count both.

### 3. Tier B (1 M orders): scale

```sh
V="--vendor <name> --tier b"          # add --database/--collection if the product needs them

# Seed: 100,000 customers, 1,000,000 orders, 2,300,000 lines (about a minute)
.venv/bin/python -m bench $V seed --supplemental-logging

# Start the product, then wait for the snapshot to complete
.venv/bin/python -m bench $V watch --target 1000000 --lines-target 2300000 --stall 900
.venv/bin/python -m bench $V reconcile --phase snapshot --sample 0.01

# Sustained load: run the lag probes in a second terminal while the load runs
.venv/bin/python -m bench $V load --rate 200 --seconds 1800 --seed 2
.venv/bin/python -m bench $V lag --samples 60 --interval 30
.venv/bin/python -m bench $V reconcile --phase load --touched results/runs/<run>/*-load.json
```

Rules that matter at this tier:

- **The document count is not a completion signal.** A product that joins as data arrives can
  write all 1 M order documents before their lines have landed (one published run had 79 % of
  lines present at that moment). Always pass `--lines-target`.
- **The load opens one Oracle connection per 5 changes per second** (40 at 200/s), because a
  single connection over a long network path tops out at a few changes per second. Check that
  `achieved_rate` in the load result is close to 200 before using the run.
- **Give each load run its own `--seed`.** New order ids are derived from it, so a second run
  with the same seed collides with the first.
- **Run the default configuration first, then any tuning, and publish both.** The Confluent
  result changed from a 38-minute drain to a 2-minute drain with one documented setting
  (`vendors/confluent/README.md`).
- **`--stall` stops the watch, not the product.** A product that reads parent tables first can
  show zero documents for a long time; read its own progress before calling a stall.

### 4. Publish

Commit the results folder (`results/runs/<date>-<vendor>[-tierb]/`) with a `README.md` that fills
in the tables from `docs/results-template.md`, add or update `vendors/<name>/`, and open a pull
request. Redact secrets; never commit `bench.env`.

## Validating the referee

`python -m bench --vendor selfcheck perfect-sink` writes the expected documents straight into the
target collection, with no product in the loop; `reconcile` must then report PASS. Run `mutate 1`
and reconcile again: it must FAIL on exactly the touched orders. This is how to confirm the harness
before blaming a product.

## Adding a product

Create `vendors/<name>/README.md` with the exact steps you followed, every configuration file with
secrets redacted, the prerequisites the product required on the Oracle side, and the time each
step took. Run the phases above and commit the results folder. Open a pull request.

## Source requirements

Oracle 19c or later is required by most log-based CDC products (Confluent's Oracle connectors do
not support older releases). `infra/` provisions a suitable Amazon RDS for Oracle instance. The
harness itself works on any Oracle the `python-oracledb` driver can reach; for servers older than
12.1 set `ORACLE_CLIENT_DIR` to an Instant Client directory.

## License

Apache License 2.0. See `LICENSE`.
