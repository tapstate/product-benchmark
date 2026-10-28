# Tapstate Cloud

Route: one Oracle source, one pipeline with a `nest` transform, one Atlas destination. The
pipeline definition is `pipeline.json`; it is submitted through the console's pipeline builder or
the API.

Setup order and what to record:

1. Oracle prerequisites: ARCHIVELOG, supplemental logging on the three tables (done by
   `python -m bench seed --supplemental-logging`), a user with LogMiner read access.
2. Cluster, Oracle source with connection test, Atlas destination with connection test.
3. Pipeline from `pipeline.json`, started in snapshot-and-CDC mode.
4. Record the first correct document time (`bench lag`).
