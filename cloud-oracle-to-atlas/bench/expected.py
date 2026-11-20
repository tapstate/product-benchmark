"""Expected target documents, computed from source rows with plain Python.

The expectation never touches any vendor: it is what the source says the
nested document must contain. Outer semantics: an order without lines carries
an empty array, an order whose customer row is missing carries None.
"""


def nest_orders(orders, lines, customers):
    by_order = {}
    for line in lines:
        by_order.setdefault(line["ORDER_ID"], []).append(line)
    cust = {c["CUSTOMER_ID"]: c for c in customers}
    docs = []
    for order in orders:
        doc = dict(order)
        own = sorted(by_order.get(order["ORDER_ID"], []), key=lambda r: r["LINE_NO"])
        doc["lines"] = [{k: v for k, v in r.items() if k != "ORDER_ID"} for r in own]
        doc["customer"] = cust.get(order["CUSTOMER_ID"])
        docs.append(doc)
    return docs
