import datetime as dt
import unittest
from decimal import Decimal

from bench import fixture as F
from bench.expected import nest_orders
from bench.reconcile import compare


def tier_a_docs():
    return nest_orders(list(F.orders("a")), list(F.lines("a")), list(F.customers("a")))


class FixtureTest(unittest.TestCase):
    def test_counts_match_generators(self):
        exp = F.expected_counts("a")
        self.assertEqual(exp["BENCH_ORDERS"], 200)
        self.assertEqual(exp["BENCH_CUSTOMERS"], 40)
        self.assertEqual(exp["BENCH_LINES"], len(list(F.lines("a"))))
        # the closed-form count must agree with the generator on a non-multiple of 20
        self.assertEqual(F.expected_counts("a")["BENCH_LINES"], sum(len(F.line_rows_for(o)) for o in range(1, 201)))

    def test_edge_cases(self):
        docs = {d["ORDER_ID"]: d for d in tier_a_docs()}
        self.assertEqual(docs[10]["lines"], [])            # every 10th order has no lines
        self.assertIsNone(docs[25]["customer"])            # every 25th order has no customer row
        self.assertEqual([l["LINE_NO"] for l in docs[3]["lines"]], [1, 2, 3, 4])
        self.assertEqual(docs[1]["customer"]["TIER"], "bronze")  # order 1 -> customer 2


class ReconcileTest(unittest.TestCase):
    def as_target(self, d):
        """What a correct sink would store: _id, uppercase keys, nested array and object."""
        t = {"_id": d["ORDER_ID"], **{k: v for k, v in d.items() if k not in ("lines", "customer")}}
        t["lines"] = [dict(l) for l in d["lines"]]
        t["customer"] = dict(d["customer"]) if d["customer"] else None
        return t

    def test_identical_passes(self):
        docs = tier_a_docs()
        self.assertTrue(compare(docs, [self.as_target(d) for d in docs]).ok)

    def test_case_and_type_tolerance(self):
        docs = tier_a_docs()
        tgt = []
        for d in docs:
            t = self.as_target(d)
            t = {k.lower(): v for k, v in t.items()}
            t["lines"] = [{k.lower(): (float(v) if k == "PRICE" else v) for k, v in l.items()} for l in t["lines"]]
            t["lines"].reverse()  # array order is not asserted
            tgt.append(t)
        self.assertTrue(compare(docs, tgt).ok)

    def test_differences_are_classified(self):
        docs = tier_a_docs()
        tgt = [self.as_target(d) for d in docs]
        tgt[0]["STATUS"] = "shipped"                                  # value
        tgt[1]["ORDER_TS"] = 1767225602000                            # date stored as integer -> type
        tgt[2]["customer"]["TIER"] = "stale"                          # nested
        tgt[3]["lines"].pop()                                         # nested
        del tgt[4]["CUSTOMER_ID"]                                     # absent
        tgt.pop()                                                     # missing
        tgt.append({"_id": 999, "ORDER_ID": 999})                     # extra
        res = compare(docs, tgt)
        kinds = {(d.key, d.field): d.kind for d in res.diffs}
        self.assertEqual(kinds[(1, "STATUS")], "value")
        self.assertEqual(kinds[(2, "ORDER_TS")], "type")
        self.assertEqual(kinds[(3, "customer")], "nested")
        self.assertEqual(kinds[(4, "lines")], "nested")
        self.assertEqual(kinds[(5, "CUSTOMER_ID")], "absent")
        self.assertEqual(res.missing, [200])
        self.assertEqual(res.extra, ["999"])
        self.assertFalse(res.ok)

    def test_null_lines_equal_empty(self):
        docs = tier_a_docs()
        tgt = [self.as_target(d) for d in docs]
        tgt[9]["lines"] = None  # order 10 has no lines
        self.assertTrue(compare(docs, tgt).ok)

    def test_millisecond_dates_pass(self):
        docs = tier_a_docs()
        tgt = [self.as_target(d) for d in docs]
        tgt[0]["ORDER_TS"] = docs[0]["ORDER_TS"].replace(tzinfo=dt.timezone.utc)
        tgt[0]["customer"]["CREATED"] = docs[0]["customer"]["CREATED"] + dt.timedelta(microseconds=400)
        self.assertTrue(compare(docs, tgt).ok)


if __name__ == "__main__":
    unittest.main()
