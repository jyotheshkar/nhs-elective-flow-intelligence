# AWS deployment and evidence guide

Status: implementation prepared and offline-tested; NOT deployed to AWS. No NHS production use or assurance is claimed.

## Business requirement and boundary

Help an operational analyst investigate provider x treatment-function waiting-list deterioration using published monthly NHS England RTT statistics. The system must preserve provenance, expose model limitations and keep a previously approved release available when refreshes fail. It never accepts patient-level or patient-identifiable records.

Target deployment: eu-west-2 (London). App Runner supports London. This is a public portfolio API with no user accounts; moving to patient-level data would require a separate design and organisational assessment. TLS and a UK region alone do not establish NHS compliance.

The existing Next.js dashboard remains on Vercel. This is explicitly a hybrid deployment, not an all-AWS frontend claim. Change NEXT_PUBLIC_API_BASE_URL only after the AWS API passes acceptance checks, then redeploy the frontend. The current Render deployment remains an independent fallback until AWS is demonstrated.

## Components and labelled connections

1. Amazon EventBridge Scheduler invokes Amazon ECS RunTask on Mondays at 08:00 Europe/London. NHS source data is monthly; weekly discovery allows publication/revision detection without permanent compute.
2. ECS on AWS Fargate pulls an immutable-tagged image from Amazon ECR. A 1-vCPU / 4-GB task discovers HTTPS NHS workbooks and executes the existing Python analytical build.
3. The worker validates canonical grain, official-data marker, expected periods, source coverage, nonnegative pathway counts, and no reporting-month regression versus the pinned release. It uploads source workbooks under raw/ and analytical artifacts under releases/<id>/ to private, encrypted, versioned Amazon S3.
4. The manifest is written last, with SHA-256 and byte size for every expected file. This is an application-level commit marker. Unique IDs plus conditional writes prevent accidental overwrite in this worker; this is not S3 Object Lock / WORM.
5. An operator reviews candidate provenance, source changes, model metrics, data-quality findings and regression results. A CloudFormation update pins the approved ReleaseId. Publication and API deployment are intentionally separate.
6. AWS App Runner downloads only that release using an IAM instance role scoped to its prefix. It verifies hashes and sizes before starting FastAPI. The existing process-lifetime caches are safe because each deployment pins one immutable warehouse.
7. The browser receives the Next.js UI from Vercel; the UI calls the App Runner HTTPS API. FastAPI uses local read-only DuckDB, never a shared writable DuckDB file on S3.
8. Amazon CloudWatch receives batch logs and refresh-failure metrics. Amazon EventBridge task-stop events notify an Amazon SNS topic, including successful stops so an OOM or killed task is not silently missed. SNS subscriptions require confirmation. The scheduler-target-error alarm is grouped at the default schedule-group level.

## Deploy in stages

Prerequisites: AWS CLI configured with the intended account, Docker, AWS permissions to create IAM/network/compute resources, and an email for alerts. Review the AWS account and estimated bill before creating resources. Commands below create chargeable resources when executed; they have not been run here.

From the repository root in PowerShell:

```powershell
$region = 'eu-west-2'
$stack = 'nhs-elective-flow'
$alert = 'YOUR_CONFIRMED_EMAIL'
aws sts get-caller-identity
aws cloudformation validate-template --template-body file://infra/aws/template.json --region $region
aws cloudformation deploy --template-file infra/aws/template.json --stack-name $stack --region $region --capabilities CAPABILITY_IAM --parameter-overrides AlertEmail=$alert DeployApi=false ScheduleState=DISABLED
$repo = aws cloudformation describe-stacks --stack-name $stack --region $region --query "Stacks[0].Outputs[?OutputKey=='ImageRepository'].OutputValue | [0]" --output text
$registry = $repo.Split('/')[0]
$tag = 'release-20261024-1'
aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $registry
docker build --platform linux/amd64 -f infra/aws/Dockerfile -t "${repo}:$tag" .
docker push "${repo}:$tag"
aws cloudformation deploy --template-file infra/aws/template.json --stack-name $stack --region $region --capabilities CAPABILITY_IAM --parameter-overrides AlertEmail=$alert ImageTag=$tag DeployApi=false ScheduleState=DISABLED
```

Use the stack outputs ClusterArn, TaskDefinition, SubnetId and SecurityGroupId in an ECS RunTask request (FARGATE, awsvpc, assignPublicIp ENABLED). Run `./infra/aws/run-refresh.ps1 -StackName $stack -Region $region` for the one-off initial refresh; inspect the returned ECS failures array, CloudWatch log stream and task exit code. The schedule remains disabled until the initial run is verified.

Review the emitted release_id and download its manifest. Compare the source periods and audit rows with the NHS publications. Verify source revisions, fact-grain uniqueness, no unexplained source omissions, quality findings, current forecast accuracy and scenario invariants. Unusual movements remain review findings, not automatically source errors. Run the local acceptance suite against the exact candidate before approval. Record reviewer, date, release ID, image tag, checks and any accepted limitations in a release note.

```powershell
$release = 'EXACT_RELEASE_ID_FROM_SUCCESSFUL_RUN'
aws cloudformation deploy --template-file infra/aws/template.json --stack-name $stack --region $region --capabilities CAPABILITY_IAM --parameter-overrides AlertEmail=$alert ImageTag=$tag DeployApi=true ReleaseId=$release ScheduleState=ENABLED
```

Do not enable the API with the bootstrap value not-yet-published. Verify /health has warehouse_available=true and data_mode=OFFICIAL_NHS_PUBLIC; /api/v1/metadata must match the reviewed reporting period. Test overview, rankings, one service history, CSV export and the 0% scenario against the local candidate before changing the frontend API URL. Confirm browser CORS and failure states. Record the API URL, region, deployed image digest and release ID; only then describe AWS as deployed on a CV.

## Acceptance targets (proposed, not measured SLA)

- Warm dashboard API p95 < 1 second for 10 concurrent readers, measured over 100 representative requests.
- Refresh completes within 60 minutes or exits nonzero; task-stop notification covers kill/OOM failures.
- A failed refresh never changes the pinned serving release.
- RPO: previous approved publication release. RTO target: restore/pin a retained release within 30 minutes after access is available. Demonstrate this; do not call it an achieved SLA.
- Monthly publication lag is visible. Do not imply a weekly job makes the underlying data real time.
- Redrive a failed launch manually after root-cause analysis. Scheduler retry is disabled to avoid unobserved duplicate expensive rebuilds.

## Remaining cloud verification

Offline tests cover download/hash/path/manifest contracts and template references/defaults. AWS CloudFormation service-schema validation, Docker image build, IAM execution, ECR scanning, live ingestion, alarm delivery, App Runner boot, browser CORS, performance and rollback drills still require an AWS deployment. No cost has been incurred by these prepared files.

## Sources checked 24 October 2026

- App Runner endpoints including London: https://docs.aws.amazon.com/general/latest/gr/apprunner.html
- App Runner concepts/configurations: https://docs.aws.amazon.com/apprunner/latest/dg/architecture.html
- App Runner ECR source and access role: https://docs.aws.amazon.com/apprunner/latest/dg/service-source-image.html
- Scheduler to ECS: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html
- Well-Architected six pillars: https://docs.aws.amazon.com/wellarchitected/latest/userguide/waf.html
