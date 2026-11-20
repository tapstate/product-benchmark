"""Deterministic source rows for the order-document scenario.

Three tables, generated from the ids alone so that any run can be reproduced
and any difference traced to the row that produced it:

  BENCH_CUSTOMERS (CUSTOMER_ID, NAME, TIER, CREATED)
  BENCH_ORDERS    (ORDER_ID, CUSTOMER_ID, STATUS, ORDER_TS)
  BENCH_LINES     (ORDER_ID, LINE_NO, SKU, QTY, PRICE)

Edge cases are deliberate: every 10th order has no lines (empty array), every
25th order points at a customer that does not exist (missing embedded object).
"""

import datetime as dt
from decimal import Decimal

TIERS = {
    # tier: (customers, orders)
    "a": (40, 200),
    "b": (100_000, 1_000_000),
    "c": (1_000_000, 10_000_000),
}

TABLES = {
    "BENCH_CUSTOMERS": (["CUSTOMER_ID"], [("CUSTOMER_ID", "int"), ("NAME", "varchar"), ("TIER", "varchar20"),
                                           ("CREATED", "ts")]),
    "BENCH_ORDERS": (["ORDER_ID"], [("ORDER_ID", "int"), ("CUSTOMER_ID", "int"), ("STATUS", "varchar20"),
                                    ("ORDER_TS", "ts")]),
    "BENCH_LINES": (["ORDER_ID", "LINE_NO"], [("ORDER_ID", "int"), ("LINE_NO", "int"), ("SKU", "varchar20"),
                                              ("QTY", "int"), ("PRICE", "dec")]),
}

ORACLE_TYPES = {"int": "NUMBER(10)", "dec": "NUMBER(18,4)", "varchar": "NVARCHAR2(200)",
                "varchar20": "VARCHAR2(20)", "ts": "TIMESTAMP(6)"}

TIER_NAMES = ["gold", "silver", "bronze"]
NAMES = ["Customer", "Kunde", "Cliente", "Zoe Saldana", "O'Brien"]


def customer_row(c):
    return {"CUSTOMER_ID": c, "NAME": f"{NAMES[c % len(NAMES)]} {c}", "TIER": TIER_NAMES[c % 3],
            "CREATED": dt.datetime(2020, 1, 1) + dt.timedelta(minutes=c)}


def order_row(o, customers):
    cust = customers + 1000 + o if o % 25 == 0 else (o % customers) + 1
    return {"ORDER_ID": o, "CUSTOMER_ID": cust, "STATUS": "open",
            "ORDER_TS": dt.datetime(2026, 1, 1) + dt.timedelta(seconds=o)}


def line_rows_for(o):
    if o % 10 == 0:
        return []
    return [{"ORDER_ID": o, "LINE_NO": n, "SKU": f"SKU-{(o * 7 + n) % 50:03d}", "QTY": n,
             "PRICE": Decimal(o * 3 + n) / Decimal(4)} for n in range(1, (o % 4) + 2)]


def customers(tier):
    n, _ = TIERS[tier]
    return (customer_row(c) for c in range(1, n + 1))


def orders(tier):
    n_cust, n_ord = TIERS[tier]
    return (order_row(o, n_cust) for o in range(1, n_ord + 1))


def lines(tier):
    _, n_ord = TIERS[tier]
    for o in range(1, n_ord + 1):
        yield from line_rows_for(o)


def expected_counts(tier):
    n_cust, n_ord = TIERS[tier]
    n_lines = sum(len(line_rows_for(o)) for o in range(1, min(n_ord, 20) + 1)) * (n_ord // 20) \
        + sum(len(line_rows_for(o)) for o in range(n_ord // 20 * 20 + 1, n_ord + 1))
    return {"BENCH_CUSTOMERS": n_cust, "BENCH_ORDERS": n_ord, "BENCH_LINES": n_lines}


def batched(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
