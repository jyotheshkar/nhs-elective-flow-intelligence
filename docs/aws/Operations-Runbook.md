# Operations, release recovery and incident drill

## Normal refresh

1. Verify the weekly schedule is enabled only after the image and first release work.
2. Confirm the ECS task stopped with exitCode 0 and emitted refresh_complete. A successful Scheduler invocation only means ECS accepted RunTask; it does not establish pipeline success.
3. Download the candidate manifest. Check expected reporting months, all three source workbook families, official marker, row counts, revisions, quality findings and backtest results.
4. Review source changes and run the application acceptance checks. Preserve the current ReleaseId and image tag.
5. Pin the reviewed candidate with CloudFormation. Check App Runner logs and /health and compare metadata and selected figures to the candidate before declaring success.

## Missing/failed download or workbook schema change

- The build exits nonzero or publication gate refuses source coverage. The pinned API does not change.
- Inspect ECS logs and task stoppedReason. Determine whether the NHS publication moved, a workbook changed or a network issue occurred.
- Repair discovery/mapping in a new immutable image tag, run existing unit/API checks and then rerun the batch. Do not hand-edit released metrics or silently treat missing activity as zero.
- If legitimate missing data prevents publication, record the accepted limitation and revise the gate through code review; never remove it solely to obtain a green build.

## Candidate looks wrong despite successful build

Keep serving the previous release. Review data_source_type, source timestamps/checksums, canonical grain, treatment-function exclusions, weighted aggregations, data-quality findings and backtest slices. A numerical quality score alone does not authorise promotion. Capture an issue with reproduction, expected/actual behaviour and affected release ID.

## API release fails to start or checksum mismatch

App Runner should not receive a listening process until all expected files pass checksums and size checks. Inspect application/service logs; compare RELEASE_ID, permissions and S3 object keys. Restore the previous ReleaseId and ImageTag through CloudFormation. Test health, metadata, rankings, one detail page and 0% scenario. Record actual restoration duration against the proposed 30-minute target.

## Corrupt/accidentally overwritten S3 object

The worker uses unique prefixes and conditional PutObject. Versioning preserves prior object versions, but there is no Object Lock. The deployment operator may restore the correct version to a new reviewed release ID and manifest, then pin it. Never change only the manifest hash to make damaged data pass. Use original source checksums to rebuild if integrity cannot be established.

## Security incident / suspected unexpected bill

Pause the App Runner service and disable the schedule after preserving relevant logs and identifying the affected workload. Revoke the compromised principal, not all unrelated account access. Review AWS audit records available in the account, object versions and ECR changes. The template does not configure a dedicated CloudTrail trail or data-event logging; enable them if the operational requirement justifies their costs. Diagnose before resuming. MaxSize=1 is a scale limit, not a spending cap.

## Teardown

Disable the schedule and pause/delete the App Runner service when the demo is not needed. CloudFormation retains the S3 bucket and ECR repository, so deleting the stack does not delete source/release evidence or image rollback targets and does not remove their storage charges. Review and explicitly remove retained resources only after deciding which evidence to preserve. Confirm alert subscriptions and actual bill in the account.

## Drill evidence to collect

Date/time, operator, account/region, image digest, old/new release IDs, starting fault, observed notification, checks performed, health/metric comparison and elapsed restoration time. These are blank until a real drill is executed; do not replace them with assumed success.
