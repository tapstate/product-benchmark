"""Command line entry point: python -m bench <command> [options].

Credentials come from an env file (default ./bench.env, see bench.env.example);
nothing secret is written to results.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time

from . import fixture as F
from .atlas import Atlas
from .oracle import Oracle
from .reconcile import compare


def load_env(path):
    env = dict(os.environ)
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_result(args, name, payload):
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{name}.json")
    payload = {"at": now(), "vendor": args.vendor, "tier": args.tier, **payload}
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=1, default=str)
    print(f"-> {path}")
    return payload


def cmd_seed(args, env):
    db = Oracle(env).open()
    t0 = time.time()
    expected = db.seed(args.tier)
    if args.supplemental_logging:
        db.supplemental_logging()
    counts = db.counts()
    db.close()
    ok = all(counts[t] == expected[t] for t in expected)
    write_result(args, "seed", {"seconds": round(time.time() - t0, 1), "expected": expected, "counts": counts,
                                "result": "PASS" if ok else "FAIL"})


def cmd_mutate(args, env):
    db = Oracle(env).open()
    t0 = time.time()
    touched = db.mutate(args.round, args.tier)
    db.close()
    write_result(args, f"mutate-round{args.round}", {"round": args.round, "committed_at": now(),
                                                      "seconds": round(time.time() - t0, 2),
                                                      "touched_orders": touched})


def cmd_delete_order(args, env):
    db = Oracle(env).open()
    db.delete_order(args.order_id)
    db.close()
    write_result(args, f"delete-order{args.order_id}", {"order_id": args.order_id, "committed_at": now()})


def cmd_load(args, env):
    db = Oracle(env).open()
    touched, n = db.load(args.tier, args.rate, args.seconds, seed=args.seed)
    db.close()
    write_result(args, "load", {"rate": args.rate, "seconds": args.seconds, "transactions": n,
                                "touched_orders": touched})


def cmd_lag(args, env):
    """Insert a probe order, poll the target until it is correct, report the delay."""
    db = Oracle(env).open()
    atlas = Atlas(env).open()
    samples = []
    for i in range(args.samples):
        marker_id = 900_000_000 + int(time.time()) % 100_000_000 * 10 + i % 10
        t_commit = db.marker(marker_id)
        expected = db.documents([marker_id])
        seen = None
        while time.time() - t_commit < args.timeout:
            docs = atlas.documents(args.database, args.collection, [marker_id])
            if docs and compare(expected, docs).ok:
                seen = time.time() - t_commit
                break
            time.sleep(args.poll)
        samples.append({"marker": marker_id, "lag_seconds": None if seen is None else round(seen, 2)})
        print(f"  probe {marker_id}: {'timeout' if seen is None else f'{seen:.2f}s'}")
        if i + 1 < args.samples:
            time.sleep(args.interval)
    db.close()
    lags = sorted(s["lag_seconds"] for s in samples if s["lag_seconds"] is not None)
    stats = {"p50": lags[len(lags) // 2] if lags else None, "max": lags[-1] if lags else None,
             "timeouts": len(samples) - len(lags)}
    write_result(args, "lag", {"samples": samples, **stats})


def sample_ids(tier, fraction, seed="bench"):
    _, n_ord = F.TIERS[tier]
    out = []
    for o in range(1, n_ord + 1):
        h = int(hashlib.sha1(f"{seed}:{o}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        if h < fraction:
            out.append(o)
    return out


def cmd_reconcile(args, env):
    db = Oracle(env).open()
    atlas = Atlas(env).open()
    t0 = time.time()
    order_ids = None
    mode = "full"
    if args.sample or args.touched:
        ids = set(sample_ids(args.tier, args.sample)) if args.sample else set()
        for path in args.touched or []:
            with open(path) as fh:
                touched = json.load(fh).get("touched_orders", [])
            ids.update(touched[-args.last:] if args.last else touched)
        order_ids = sorted(ids)
        mode = f"sample={args.sample} touched={len(args.touched or [])} files last={args.last} ({len(order_ids)} orders)"
    expected = db.documents(order_ids)
    actual = atlas.documents(args.database, args.collection, order_ids)
    res = compare(expected, actual)
    payload = {"phase": args.phase, "mode": mode, "seconds": round(time.time() - t0, 1),
               "source_counts": db.counts(), "target_count": atlas.count(args.database, args.collection),
               **res.as_dict()}
    db.close()
    print(res.summary())
    write_result(args, f"reconcile-{args.phase}", payload)
    return 0 if res.ok else 1


def cmd_expected(args, env):
    """Write the expected documents (what a correct target must contain) as JSON."""
    db = Oracle(env).open()
    docs = db.documents()
    db.close()
    write_result(args, "expected", {"documents": docs})


def cmd_watch(args, env):
    """Record the target collection every --every seconds until it is complete or stalls (--stall
    seconds without change): the snapshot throughput and backlog-drain measurement. Completion
    means the document count reached --target and, when --lines-target is given, the nested lines
    summed over all documents reached it too. A parent-first pipeline emits an order before its
    lines and customer have arrived, so the document count alone can hit the target early."""
    atlas = Atlas(env).open()
    t0 = time.time()
    samples = []
    last_change = t0
    last = None
    while True:
        if args.lines_target or args.shape:
            shape = atlas.shape(args.database, args.collection)
        else:
            shape = {"docs": atlas.count(args.database, args.collection)}
        now = time.time()
        samples.append({"t": round(now - t0, 1), "at": now_iso(), **shape})
        print(f"  {now - t0:7.0f}s  " + "  ".join(f"{k}={v}" for k, v in shape.items()), flush=True)
        key = tuple(shape.values())
        if key != last:
            last, last_change = key, now
        complete = (not args.target or shape["docs"] >= args.target) and \
                   (not args.lines_target or shape["lines"] >= args.lines_target)
        if (args.target or args.lines_target) and complete:
            break
        if (now - last_change) >= args.stall or (now - t0) >= args.timeout:
            break
        time.sleep(args.every)
    rate = None
    if len(samples) > 1 and samples[-1]["t"] > 0:
        rate = round((samples[-1]["docs"] - samples[0]["docs"]) / samples[-1]["t"], 1)
    lines_rate = None
    if args.lines_target and len(samples) > 1 and samples[-1]["t"] > 0:
        lines_rate = round((samples[-1]["lines"] - samples[0]["lines"]) / samples[-1]["t"], 1)
    write_result(args, "watch-" + args.label, {"target": args.target, "lines_target": args.lines_target,
                                                "final": samples[-1], "seconds": samples[-1]["t"],
                                                "complete": complete, "docs_per_second": rate,
                                                "lines_per_second": lines_rate, "samples": samples})


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def cmd_perfect_sink(args, env):
    """Write the expected documents straight into the target: validates the referee and the
    target contract without any vendor in the loop (reconcile must then PASS)."""
    db = Oracle(env).open()
    docs = db.documents()
    db.close()
    n = Atlas(env).open().write_perfect(args.database, args.collection, docs)
    write_result(args, "perfect-sink", {"documents": n})


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bench")
    ap.add_argument("--env", default="bench.env")
    ap.add_argument("--tier", choices=list(F.TIERS), default="a")
    ap.add_argument("--vendor", default=os.environ.get("BENCH_VENDOR", "unknown"))
    ap.add_argument("--out", default=None, help="results folder (default results/runs/<date>-<vendor>)")
    ap.add_argument("--database", default=None, help="target database (default cr_<vendor>)")
    ap.add_argument("--collection", default="orders")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="drop, create and fill the three tables")
    s.add_argument("--supplemental-logging", action="store_true")
    s = sub.add_parser("mutate", help="one scripted change round")
    s.add_argument("round", type=int)
    s = sub.add_parser("delete-order")
    s.add_argument("order_id", type=int)
    s = sub.add_parser("load", help="sustained random change mix")
    s.add_argument("--rate", type=float, default=200)
    s.add_argument("--seconds", type=int, default=1800)
    s.add_argument("--seed", type=int, default=1)
    s = sub.add_parser("lag", help="probe orders: commit-to-correct-document delay")
    s.add_argument("--samples", type=int, default=5)
    s.add_argument("--interval", type=float, default=30)
    s.add_argument("--poll", type=float, default=1)
    s.add_argument("--timeout", type=float, default=600)
    s = sub.add_parser("reconcile", help="compare target documents with what the source says")
    s.add_argument("--phase", default="snapshot")
    s.add_argument("--sample", type=float, default=None, help="fraction of orders to compare, e.g. 0.01")
    s.add_argument("--touched", nargs="*", help="mutate/load result files whose touched orders to compare")
    s.add_argument("--last", type=int, default=None, help="with --touched: only the last N touched orders per file")
    s = sub.add_parser("watch", help="record the target count over time until it reaches --target or stalls")
    s.add_argument("--target", type=int, default=None, help="document count that marks completion")
    s.add_argument("--lines-target", type=int, default=None,
                   help="total nested lines (summed over all documents) that marks completion")
    s.add_argument("--shape", action="store_true",
                   help="track nested lines and customers as well as the count, so a drain stalls only when "
                        "the whole collection shape has stopped changing")
    s.add_argument("--every", type=float, default=30)
    s.add_argument("--stall", type=float, default=600, help="stop when the count has not changed for this long")
    s.add_argument("--timeout", type=float, default=4 * 3600)
    s.add_argument("--label", default="snapshot")
    sub.add_parser("expected", help="dump the expected documents")
    sub.add_parser("perfect-sink", help="write the expected documents into the target (referee self-check)")
    args = ap.parse_args(argv)
    args.database = args.database or f"cr_{args.vendor}"
    args.out = args.out or os.path.join("results", "runs", f"{dt.date.today():%Y-%m-%d}-{args.vendor}")
    env = load_env(args.env)
    fn = {"seed": cmd_seed, "mutate": cmd_mutate, "delete-order": cmd_delete_order, "load": cmd_load,
          "lag": cmd_lag, "reconcile": cmd_reconcile, "expected": cmd_expected,
          "perfect-sink": cmd_perfect_sink, "watch": cmd_watch}[args.cmd]
    return fn(args, env) or 0


if __name__ == "__main__":
    sys.exit(main())
