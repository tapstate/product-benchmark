# Fivetran

Fivetran has no MongoDB connector destination; MongoDB is available only as an Activations
(reverse ETL) destination. The documented route for this job is therefore:

1. Oracle connector to a warehouse destination (Snowflake or BigQuery), incremental sync.
2. A SQL or dbt model in the warehouse that builds the nested document
   (`ARRAY_AGG` / `OBJECT_CONSTRUCT` or the BigQuery equivalents).
3. An Activations sync from that model into Atlas database `cr_fivetran`, collection `orders`.

This is a scheduled batch path end to end; lag is bounded below by the sync intervals of steps 1
and 3. The run records both intervals and the warehouse cost alongside the Fivetran cost.

Files to add when the run is done: connector settings (redacted), the warehouse model, the
Activations sync definition, the sync-interval settings, and the results folder.
