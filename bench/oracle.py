"""Oracle source: schema, bulk seed, change rounds, sustained load and row readers.

Plain SQL over python-oracledb. Nothing here is specific to any vendor; every
product under test reads the same tables produced by this module.
"""

import datetime as dt
import os
import random
import time
from decimal import Decimal

from . import fixture as F

INT_COLUMNS = {n for _, cols in F.TABLES.values() for n, kind in cols if kind == "int"} | {"N"}


class Oracle:
    def __init__(self, env):
        self.env = env
        self.schema = env.get("ORACLE_SCHEMA") or env["ORACLE_USER"].upper()
        self.conn = None

    def open(self):
        import oracledb
        lib = os.path.expanduser(self.env.get("ORACLE_CLIENT_DIR", ""))
        if lib:
            try:
                oracledb.init_oracle_client(lib_dir=lib)
            except oracledb.ProgrammingError:
                pass
        oracledb.defaults.fetch_decimals = True
        p = self.env
        if p.get("ORACLE_SERVICE"):
            dsn = oracledb.makedsn(p["ORACLE_HOST"], int(p["ORACLE_PORT"]), service_name=p["ORACLE_SERVICE"])
        else:
            dsn = oracledb.makedsn(p["ORACLE_HOST"], int(p["ORACLE_PORT"]), sid=p["ORACLE_SID"])
        self.conn = oracledb.connect(user=p["ORACLE_USER"], password=p["ORACLE_PASSWORD"], dsn=dsn)
        return self

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def q(self, table):
        return f'"{self.schema}"."{table}"'

    def execute(self, sql, params=None, many=False):
        cur = self.conn.cursor()
        try:
            if many:
                cur.executemany(sql, params)
            elif params is None:
                cur.execute(sql)
            else:
                cur.execute(sql, params)
        finally:
            cur.close()

    def query(self, sql, params=None):
        """Rows as dicts; integer columns come back as int rather than Decimal."""
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params or [])
            names = [c[0].upper() for c in cur.description]
            for row in cur:
                yield {n: (int(v) if n in INT_COLUMNS and v is not None else v) for n, v in zip(names, row)}
        finally:
            cur.close()

    # -- schema ---------------------------------------------------------------
    def drop(self):
        for t in F.TABLES:
            try:
                self.execute(f"DROP TABLE {self.q(t)} PURGE")
            except Exception:
                pass
        self.conn.commit()

    def create(self):
        for t, (keys, cols) in F.TABLES.items():
            body = ", ".join(f"{n} {F.ORACLE_TYPES[k]}{' NOT NULL' if n in keys else ''}" for n, k in cols)
            self.execute(f"CREATE TABLE {self.q(t)} ({body}, PRIMARY KEY ({', '.join(keys)}))")
        self.conn.commit()

    def supplemental_logging(self):
        """Per-table ALL COLUMNS supplemental logging, needed by every log-based CDC reader."""
        for t in F.TABLES:
            self.execute(f"ALTER TABLE {self.q(t)} ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS")
        self.conn.commit()

    # -- seed -----------------------------------------------------------------
    def insert_rows(self, table, rows):
        names = [n for n, _ in F.TABLES[table][1]]
        sql = (f"INSERT INTO {self.q(table)} ({', '.join(names)}) "
               f"VALUES ({', '.join(f':{i + 1}' for i in range(len(names)))})")
        self.execute(sql, [tuple(r[n] for n in names) for r in rows], many=True)

    def seed(self, tier, batch=10_000, log=print):
        self.drop()
        self.create()
        t0 = time.time()
        for table, gen in (("BENCH_CUSTOMERS", F.customers(tier)), ("BENCH_ORDERS", F.orders(tier)),
                           ("BENCH_LINES", F.lines(tier))):
            n = 0
            for rows in F.batched(gen, batch):
                self.insert_rows(table, rows)
                self.conn.commit()
                n += len(rows)
                if n % (batch * 10) == 0:
                    log(f"  {table}: {n} rows, {time.time() - t0:.0f}s")
            log(f"  {table}: {n} rows")
        return F.expected_counts(tier)

    def counts(self):
        return {t: next(self.query(f"SELECT COUNT(*) AS N FROM {self.q(t)}"))["N"] for t in F.TABLES}

    # -- change rounds ----------------------------------------------------------
    def mutate(self, round_no, tier):
        """One scripted round: insert an order with 3 lines, ship ~28 orders, delete one line,
        upgrade one customer. Round numbers keep successive rounds on disjoint ids.
        Returns the order ids touched, for targeted reconciliation."""
        n_cust, n_ord = F.TIERS[tier]
        order_id = n_ord + round_no
        step = max(7, n_ord // 28)
        self.insert_rows("BENCH_ORDERS", [{"ORDER_ID": order_id, "CUSTOMER_ID": 1, "STATUS": "open",
                                           "ORDER_TS": dt.datetime(2026, 10, 1, 12, round_no % 60)}])
        self.insert_rows("BENCH_LINES", [{"ORDER_ID": order_id, "LINE_NO": n, "SKU": f"SKU-R{round_no}",
                                          "QTY": n, "PRICE": Decimal("9.99")} for n in (1, 2, 3)])
        shipped = [r["ORDER_ID"] for r in self.query(
            f"SELECT ORDER_ID FROM {self.q('BENCH_ORDERS')} WHERE MOD(ORDER_ID, :1) = :2", [step, round_no % step])]
        self.execute(f"UPDATE {self.q('BENCH_ORDERS')} SET STATUS = 'shipped' WHERE MOD(ORDER_ID, :1) = :2",
                     [step, round_no % step])
        self.execute(f"DELETE FROM {self.q('BENCH_LINES')} WHERE ORDER_ID = :1 AND LINE_NO = 1", [1 + round_no])
        cust = round_no % n_cust + 1
        self.execute(f"UPDATE {self.q('BENCH_CUSTOMERS')} SET TIER = 'platinum' WHERE CUSTOMER_ID = :1", [cust])
        fanout = [r["ORDER_ID"] for r in self.query(
            f"SELECT ORDER_ID FROM {self.q('BENCH_ORDERS')} WHERE CUSTOMER_ID = :1", [cust])]
        self.conn.commit()
        return sorted(set([order_id, 1 + round_no] + shipped + fanout))

    def delete_order(self, order_id):
        self.execute(f"DELETE FROM {self.q('BENCH_LINES')} WHERE ORDER_ID = :1", [order_id])
        self.execute(f"DELETE FROM {self.q('BENCH_ORDERS')} WHERE ORDER_ID = :1", [order_id])
        self.conn.commit()

    def load(self, tier, rate, seconds, seed=1, log=print):
        """Sustained random change mix at `rate` transactions per second.
        Mix: 40% new order with lines, 30% status update, 20% line delete, 10% customer tier update.
        Returns the set of order ids touched."""
        n_cust, n_ord = F.TIERS[tier]
        r = random.Random(seed)
        touched = set()
        next_id = n_ord + 1_000_000 + seed * 10_000_000
        t_end = time.time() + seconds
        n = 0
        interval = 1.0 / rate
        while time.time() < t_end:
            t = time.time()
            op = r.random()
            if op < 0.4:
                next_id += 1
                cust = r.randint(1, n_cust)
                self.insert_rows("BENCH_ORDERS", [{"ORDER_ID": next_id, "CUSTOMER_ID": cust, "STATUS": "open",
                                                   "ORDER_TS": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)}])
                self.insert_rows("BENCH_LINES", [{"ORDER_ID": next_id, "LINE_NO": k, "SKU": f"SKU-L{k}", "QTY": k,
                                                  "PRICE": Decimal(r.randint(100, 9999)) / 100} for k in (1, 2)])
                touched.add(next_id)
            elif op < 0.7:
                oid = r.randint(1, n_ord)
                self.execute(f"UPDATE {self.q('BENCH_ORDERS')} SET STATUS = :1 WHERE ORDER_ID = :2",
                             [r.choice(["shipped", "paid", "closed"]), oid])
                touched.add(oid)
            elif op < 0.9:
                oid = r.randint(1, n_ord)
                self.execute(f"DELETE FROM {self.q('BENCH_LINES')} WHERE ORDER_ID = :1 AND LINE_NO = "
                             f"(SELECT MAX(LINE_NO) FROM {self.q('BENCH_LINES')} WHERE ORDER_ID = :2)", [oid, oid])
                touched.add(oid)
            else:
                cust = r.randint(1, n_cust)
                self.execute(f"UPDATE {self.q('BENCH_CUSTOMERS')} SET TIER = :1 WHERE CUSTOMER_ID = :2",
                             [r.choice(F.TIER_NAMES + ["platinum"]), cust])
                touched.update(x["ORDER_ID"] for x in self.query(
                    f"SELECT ORDER_ID FROM {self.q('BENCH_ORDERS')} WHERE CUSTOMER_ID = :1", [cust]))
            self.conn.commit()
            n += 1
            if n % (rate * 60) == 0:
                log(f"  {n} transactions, {len(touched)} orders touched")
            time.sleep(max(0.0, interval - (time.time() - t)))
        return touched, n

    def marker(self, marker_id):
        """Insert one order with two lines whose id encodes the probe; returns the commit time."""
        self.insert_rows("BENCH_ORDERS", [{"ORDER_ID": marker_id, "CUSTOMER_ID": 1, "STATUS": "probe",
                                           "ORDER_TS": dt.datetime(2026, 1, 1)}])
        self.insert_rows("BENCH_LINES", [{"ORDER_ID": marker_id, "LINE_NO": k, "SKU": "PROBE", "QTY": k,
                                          "PRICE": Decimal("1.00")} for k in (1, 2)])
        self.conn.commit()
        return time.time()

    # -- readers --------------------------------------------------------------
    def rows(self, table, order_ids=None):
        if order_ids is None:
            return list(self.query(f"SELECT * FROM {self.q(table)}"))
        out = []
        col = "CUSTOMER_ID" if table == "BENCH_CUSTOMERS" else "ORDER_ID"
        for chunk in F.batched(order_ids, 500):
            marks = ", ".join(f":{i + 1}" for i in range(len(chunk)))
            out.extend(self.query(f"SELECT * FROM {self.q(table)} WHERE {col} IN ({marks})", list(chunk)))
        return out

    def documents(self, order_ids=None):
        """Expected documents for all orders, or for the given order ids."""
        from .expected import nest_orders
        orders = self.rows("BENCH_ORDERS", order_ids)
        lines = self.rows("BENCH_LINES", order_ids)
        if order_ids is None:
            customers = self.rows("BENCH_CUSTOMERS")
        else:
            customers = self.rows("BENCH_CUSTOMERS", sorted({o["CUSTOMER_ID"] for o in orders}))
        return nest_orders(orders, lines, customers)
