# Monthly cost planning

This is a planning model, not a bill, price quote or guaranteed maximum. No resources were deployed. Run `python infra/aws/estimate_costs.py` to reproduce `Cost-Estimate.json` and edit the inputs before a real deployment.

Target region is **London (eu-west-2)**. The public App Runner page explicitly publishes **Ireland** examples at $0.007/GB-hour provisioned memory and $0.064/vCPU-hour active CPU. Those verified Ireland rates provide the comparison baseline below; they are NOT asserted as verified London rates. Use AWS Pricing Calculator with London selected to replace the regional inputs before deploying.

| Component | Quantity and formula | Illustrative USD/month |
|---|---|---:|
| API provisioned memory | 2 GB x 730 h x $0.007 (Ireland published) | 10.22 |
| API CPU when active | 1 vCPU x 30 h x $0.064 (Ireland published) | 1.92 |
| Batch CPU/RAM | 5 runs x 20/60 h x (1 x $0.06 + 4 x $0.007); rates are planning assumptions | 0.1467 |
| Batch public IPv4 | 1 address x 1.6667 h x $0.005 | 0.0083 |
| S3 storage | 10 GB x assumed $0.03/GB-month | 0.30 |
| ECR image storage | 2 GB x $0.10/GB-month published example | 0.20 |
| Logs, metrics, 2 alarms, SNS | Planning allowance, not a quoted tariff | 3.00 |
| Requests and API egress | Planning allowance, not a quoted tariff | 1.00 |
| **Illustrative total before tax** | No free-tier/credits assumed | **16.80** |

A continuously active single API instance increases this comparison to **$61.60/month** before tax and unexpected variable charges. MaxSize=1 limits scale, not CPU activity, outbound bytes or account spending. App Runner can temporarily double instances during deployment. Budget alerts notify but do not cap spend.

No NAT gateway, ALB, RDS, SageMaker endpoint, always-running batch EC2 host or automatic App Runner deployment fee is included because the template does not use them. ECR-based image building runs locally; image scanning or enhanced scanning pricing must be reviewed in the actual account. Public source data download is inbound; images/artifacts stay in-region. Vercel usage is outside this AWS estimate.

Storage assumption includes multiple raw and processed snapshots. Raw data expires after 180 days; historical object versions after 90 days. Current release objects have no automatic expiry so a pinned API remains recoverable. Audit unused releases and images periodically. App Runner logs are service-created and need retention configured after deployment; only batch log retention is explicitly set by this template.

Before spending: select the intended account and region, estimate actual image/artifact sizes, configure AWS budget alerts and confirm notification email. Check the first bill after a controlled demonstration. Pausing the API reduces compute charges but retained storage and other account resources can still be billed.

Primary sources checked 24 October 2026:

- https://aws.amazon.com/apprunner/pricing/
- https://aws.amazon.com/fargate/pricing/ (billing dimensions; specific regional rates above remain planning assumptions)
- https://aws.amazon.com/vpc/pricing/ ($0.005 public IPv4-hour)
- https://aws.amazon.com/ecr/pricing/ ($0.10/GB-month private storage example)
- https://aws.amazon.com/s3/pricing/ (replace S3 planning assumption for the selected region)
- https://aws.amazon.com/cloudwatch/pricing/ (replace monitoring allowance with measured use)
- https://calculator.aws/
