"""Key-by-key, field-by-field comparison of expected documents and target documents.

Both sides are reduced to a canonical form so that representation differences
that carry no information (int vs Decimal, Decimal128 vs Decimal, naive vs UTC
datetimes) compare equal, while every difference in value is reported with its
key and field. A date stored as an integer, a stale nested child or a missing
array element is a difference.
"""

import datetime as dt
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

try:
    from bson import Decimal128, ObjectId
except ImportError:  # pragma: no cover
    Decimal128 = ObjectId = ()

UTC = dt.timezone.utc

# BSON dates carry milliseconds; a MongoDB target cannot keep microseconds.
MONGO = {"ts_precision": "ms"}
EXACT = {"ts_precision": "us"}


def canon(value, rules=MONGO):
    if value is None:
        return None
    if isinstance(value, bool):
        return ("bool", value)
    if Decimal128 and isinstance(value, Decimal128):
        value = value.to_decimal()
    if isinstance(value, (int, Decimal)):
        try:
            d = Decimal(value).normalize()
        except InvalidOperation:
            return ("num", str(value))
        return ("num", format(d, "f"))
    if isinstance(value, float):
        return ("num", format(Decimal(repr(value)).normalize(), "f"))
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        value = value.astimezone(UTC)
        if rules["ts_precision"] == "ms":
            value = value.replace(microsecond=value.microsecond // 1000 * 1000)
        return ("ts", value.isoformat(timespec="microseconds"))
    if isinstance(value, dt.date):
        return ("date", value.isoformat())
    if ObjectId and isinstance(value, ObjectId):
        return ("oid", str(value))
    if isinstance(value, (bytes, bytearray)):
        return ("bin", bytes(value).hex())
    if isinstance(value, str):
        return ("str", unicodedata.normalize("NFC", value))
    if isinstance(value, dict):
        return ("doc", tuple(sorted((k.upper(), canon(v, rules)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return ("arr", tuple(canon(v, rules) for v in value))
    return (type(value).__name__, str(value))


@dataclass
class FieldDiff:
    key: object
    field: str
    expected: object
    actual: object
    kind: str  # value | type | absent | nested


@dataclass
class Result:
    expected_count: int = 0
    target_count: int = 0
    missing: list = field(default_factory=list)
    extra: list = field(default_factory=list)
    diffs: list = field(default_factory=list)

    @property
    def ok(self):
        return not (self.missing or self.extra or self.diffs)

    def as_dict(self, limit=50):
        return {
            "expected": self.expected_count, "target": self.target_count,
            "missing": len(self.missing), "extra": len(self.extra), "field_diffs": len(self.diffs),
            "result": "PASS" if self.ok else "FAIL",
            "missing_keys": self.missing[:limit], "extra_keys": self.extra[:limit],
            "diffs": [{"key": d.key, "field": d.field, "kind": d.kind,
                       "expected": repr(d.expected), "actual": repr(d.actual)} for d in self.diffs[:limit]],
        }

    def summary(self):
        d = self.as_dict(limit=10)
        head = (f"expected={d['expected']} target={d['target']} missing={d['missing']} "
                f"extra={d['extra']} field_diffs={d['field_diffs']} -> {d['result']}")
        rows = [f"  missing {k}" for k in d["missing_keys"]] + [f"  extra {k}" for k in d["extra_keys"]]
        rows += [f"  {x['key']} {x['field']} ({x['kind']}): expected={x['expected']} actual={x['actual']}"
                 for x in d["diffs"]]
        return "\n".join([head] + rows)


DOC_FIELDS = ["ORDER_ID", "CUSTOMER_ID", "STATUS", "ORDER_TS", "customer", "lines"]
LINE_FIELDS = ["LINE_NO", "SKU", "QTY", "PRICE"]
CUSTOMER_FIELDS = ["CUSTOMER_ID", "NAME", "TIER", "CREATED"]


def _get(doc, name):
    """Field lookup tolerant of case: vendors emit ORDER_ID, order_id or lines/LINES."""
    if name in doc:
        return doc[name], True
    for k in doc:
        if k.upper() == name.upper():
            return doc[k], True
    return None, False


def _lines_key(line):
    v, _ = _get(line, "LINE_NO")
    return canon(v)


def _canon_lines(lines):
    if lines is None:
        return ()  # no lines: an empty array, an omitted field and null are equivalent
    if not isinstance(lines, list):
        return ("type", type(lines).__name__, str(lines)[:80])
    rows = []
    for ln in sorted(lines, key=_lines_key):
        if not isinstance(ln, dict):
            return ("type", "element", str(ln)[:80])
        rows.append(tuple(canon(_get(ln, f)[0]) for f in LINE_FIELDS))
    return tuple(rows)


def _canon_customer(c):
    if c is None:
        return None
    if not isinstance(c, dict):
        return ("type", type(c).__name__, str(c)[:80])
    return tuple(canon(_get(c, f)[0]) for f in CUSTOMER_FIELDS)


def _kind(expected, actual):
    if actual is None and expected is not None:
        return "absent"
    if type(expected) is not type(actual) and not (isinstance(expected, (int, Decimal)) and
                                                   isinstance(actual, (int, Decimal, float))):
        return "type"
    return "value"


def compare(expected_docs, target_docs):
    """expected_docs: from expected.nest_orders; target_docs: raw documents read from the target."""
    exp = {canon(d["ORDER_ID"]): d for d in expected_docs}
    ids = {canon(d["ORDER_ID"]): d["ORDER_ID"] for d in expected_docs}
    tgt = {}
    for d in target_docs:
        oid, found = _get(d, "ORDER_ID")
        if not found:
            oid = d.get("_id")
        key = canon(oid)
        if key in tgt:
            raise ValueError(f"duplicate target key {key}")
        tgt[key] = d
    res = Result(expected_count=len(exp), target_count=len(tgt))
    res.missing = sorted(ids[k] for k in exp if k not in tgt)
    res.extra = sorted(str(k[1]) if k else str(k) for k in tgt if k not in exp)
    for key in exp:
        if key not in tgt:
            continue
        e, t = exp[key], tgt[key]
        oid = ids[key]
        for name in ("CUSTOMER_ID", "STATUS", "ORDER_TS"):
            tv, found = _get(t, name)
            if not found:
                res.diffs.append(FieldDiff(oid, name, e[name], None, "absent"))
            elif canon(e[name]) != canon(tv):
                res.diffs.append(FieldDiff(oid, name, e[name], tv, _kind(e[name], tv)))
        tv, found = _get(t, "customer")
        if e["customer"] is None:
            if found and tv not in (None, {}):
                res.diffs.append(FieldDiff(oid, "customer", None, tv, "nested"))
        elif not found or _canon_customer(tv) != _canon_customer(e["customer"]):
            res.diffs.append(FieldDiff(oid, "customer", e["customer"], tv if found else None,
                                       "absent" if not found else "nested"))
        tv, found = _get(t, "lines")
        if not found:
            tv = []  # an empty array may be omitted by some sinks
        if _canon_lines(tv) != _canon_lines(e["lines"]):
            res.diffs.append(FieldDiff(oid, "lines", e["lines"], tv, "nested"))
    return res
