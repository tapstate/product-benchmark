"""MongoDB Atlas target reader, plus the perfect-sink writer used to validate the referee."""

from decimal import Decimal


def bson_ready(value):
    """Expected documents use Decimal for NUMBER columns; BSON wants int or Decimal128."""
    from bson import Decimal128
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else Decimal128(value)
    if isinstance(value, dict):
        return {k: bson_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [bson_ready(v) for v in value]
    return value


class Atlas:
    def __init__(self, env):
        self.env = env

    def open(self):
        import pymongo
        self.client = pymongo.MongoClient(self.env["ATLAS_URI"], serverSelectionTimeoutMS=15000)
        self.client.admin.command("ping")
        return self

    def collection(self, database, collection):
        return self.client[database][collection]

    def documents(self, database, collection, order_ids=None):
        coll = self.collection(database, collection)
        if order_ids is None:
            return list(coll.find({}))
        ids = list(order_ids)
        docs = list(coll.find({"$or": [{"ORDER_ID": {"$in": ids}}, {"order_id": {"$in": ids}},
                                       {"_id": {"$in": ids}}]}))
        return docs

    def write_perfect(self, database, collection, docs):
        """Replace the collection with exactly the expected documents (a perfect sink)."""
        coll = self.collection(database, collection)
        coll.delete_many({})
        if docs:
            coll.insert_many([{"_id": d["ORDER_ID"], **bson_ready(d)} for d in docs])
        return len(docs)

    def count(self, database, collection):
        return self.collection(database, collection).estimated_document_count()

    def shape(self, database, collection):
        """Document count plus the total number of nested lines and the number of documents carrying
        a customer sub-document: a parent-first pipeline can show every order long before its
        children have arrived, so the document count alone does not prove a snapshot is complete."""
        pipeline = [{"$group": {
            "_id": None,
            "docs": {"$sum": 1},
            "lines": {"$sum": {"$size": {"$ifNull": ["$lines", []]}}},
            "with_customer": {"$sum": {"$cond": [{"$ifNull": ["$customer", False]}, 1, 0]}},
        }}]
        rows = list(self.collection(database, collection).aggregate(pipeline, allowDiskUse=True))
        if not rows:
            return {"docs": 0, "lines": 0, "with_customer": 0}
        r = rows[0]
        return {"docs": r["docs"], "lines": r["lines"], "with_customer": r["with_customer"]}
