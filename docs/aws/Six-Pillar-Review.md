# Six-pillar review and architectural decisions

All controls below refer to a public aggregate-statistics portfolio workload. Implementation is prepared; AWS verification is pending.

| Pillar | Decision and reason | Demonstrable evidence | Residual risk / improvement trigger |
|---|---|---|---|
| Operational Excellence | Infrastructure as code; structured build logs; candidate promotion checklist; explicit dataset and image versions. | Template, release manifest, test report, operator release note. | A cloud run and alert delivery drill remain pending. Add automated CI/change sets after the first deployment. |
| Security | Private S3, HTTPS-only bucket policy, AES-256 at rest, no static keys, separate build/execution/API roles, no inbound ports on batch tasks, non-root container, ECR scan. | Review IAM scopes, inspect public-access settings and image findings. | Public API is deliberate for public statistics. It needs rate/abuse protection if traffic warrants it. Encryption is not proof of NHS patient-data compliance. |
| Reliability | Unique releases, manifest committed last, pre-publication checks, pinned read-only API snapshot and manual promotion; S3 bucket/images retained on stack deletion. | Hash-tamper test, failed-download test, pinned-release rollback drill. | One batch subnet is one-AZ. Failed batch can rerun later; no live care is dependent on it. The API uses managed App Runner infrastructure, with max one instance; regional disaster failover is not implemented. |
| Performance Efficiency | Forecast once per release; local DuckDB queries; small immutable warehouse; API caches survive until redeploy. | Backtest report and representative API latency/concurrency measurements. | 2-GB API memory and max one instance are starting hypotheses. Increase only after memory/load testing. |
| Cost Optimization | Fargate only during refresh, no NAT gateway, bounded API scale, no always-on database, manual deployment from ECR, 30-day batch logs. | Itemised planning model plus actual AWS bill after deployment. | Public API can remain CPU-active under abuse. Max instances limits scale but is not a bill cap; set account budget alerts before deployment. |
| Sustainability | Shared public-source data, columnar storage, precomputation, finite logs/raw retention and no idle batch worker. | Refresh runtime/bytes, repeated-build comparison and retention settings. | Weekly full rebuild currently re-downloads/recomputes history. Incremental checksum/revision-aware builds are the next useful optimisation once correctness is proven; no carbon reduction is claimed. |

## Decisions to explain at interview

**Why DuckDB rather than an RDS database?** The current warehouse is analytical, comparatively small and immutable per release. A local read-only snapshot avoids a permanently billed database and keeps the existing tested analytics intact. Concurrent independent API instances can each read their own copy. Never mount a writable DuckDB file across tasks.

**Why no SageMaker, Spark, Kafka or Kubernetes?** Monthly public workbooks and a few thousand short time series do not currently justify their operational cost. Existing interpretable Python forecasting remains the analytical component; AWS runs the workload and protects its delivery.

**Why weekly processing and manual approval?** Monthly source publications can be revised or delayed. A schedule discovers updates; an operator checks the actual data vintage and quality before replacing a functioning release. Automated ingestion is not the same as automatic publication.

**Why retain Vercel?** The existing frontend already works. Moving it does not establish additional clinical or analytical value for these applications. The AWS evidence concentrates on data delivery, access controls, recovery and cost. The architecture diagram labels the external frontend explicitly.

**Why London?** Demonstrates a concrete UK-region design. Only public data is in scope. A future trust-owned deployment must derive geography, access and retention requirements from that organisation rather than infer them from this portfolio.

**What is a worthwhile extension?** A genuine Power BI report reading validated exports, with a semantic model and correct weighted metrics. Add service-specific requirements when a vacancy asks for them. Avoid claiming software or cloud operating experience until the report/deployment has actually been exercised.
