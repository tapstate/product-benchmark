# Design decisions

- **One order document, not a customer document, is the primary scenario.** One order with a
  lines array and a customer object is the smallest shape that exercises every nesting behavior
  that separates products: child insert and delete rewriting the parent array, parent update
  fanning out to many documents, whole-document delete. A customer document with orders with
  lines is the phase-2 stress test.
- **The referee is plain Python over source rows.** No vendor code computes the expectation.
- **Array order is not asserted.** Several products cannot guarantee it; asserting it would turn
  a documented limitation into a correctness failure. It is reported in the feature matrix instead.
- **Deterministic rows.** Every row is a function of its id, so a difference points at the
  statement that produced it and a run can be repeated on any Oracle.
- **Evidence or nothing.** A number that has no run folder is not published.
