# product-benchmark

Reproducible benchmarks for one everyday data-integration job: **keep nested MongoDB documents in
sync with their source tables**, initial load plus continuous change capture. Each benchmark runs
every product on the same source, the same changes and the same checks, and publishes the harness
and the evidence so that anyone can rerun it and check a result.

| Benchmark | Deployment | Job | Compares |
|---|---|---|---|
| [`cloud-oracle-to-atlas/`](cloud-oracle-to-atlas/) | managed cloud services | Oracle tables to MongoDB Atlas | Tapstate Cloud, Confluent Cloud, Fivetran |
| [`self-hosted-nest-vs-kafka-flink/`](self-hosted-nest-vs-kafka-flink/) | self-hosted, one 2 CPU / 8 GB engine | MongoDB collections to MongoDB | Tapstate NEST, Debezium + Kafka + Flink |

The two benchmarks are independent. Each folder holds its own README, harness, configuration and
results, and is run from inside that folder.

## License

Apache License 2.0. See `LICENSE`.
