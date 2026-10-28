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
sustained change mix, and `reconcile --sample 0.01 --touched ...` instead of a full compare.

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
