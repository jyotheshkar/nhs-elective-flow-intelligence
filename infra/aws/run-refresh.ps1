param(
    [string]$StackName = 'nhs-elective-flow',
    [string]$Region = 'eu-west-2'
)
$ErrorActionPreference = 'Stop'
$stackJson = aws cloudformation describe-stacks --stack-name $StackName --region $Region --output json
if ($LASTEXITCODE -ne 0) { throw 'Could not read the requested CloudFormation stack.' }
$stack = $stackJson | ConvertFrom-Json
$values = @{}
foreach ($entry in $stack.Stacks[0].Outputs) { $values[$entry.OutputKey] = $entry.OutputValue }
$request = @{
    cluster = $values.ClusterArn
    taskDefinition = $values.TaskDefinition
    launchType = 'FARGATE'
    count = 1
    platformVersion = 'LATEST'
    networkConfiguration = @{
        awsvpcConfiguration = @{
            assignPublicIp = 'ENABLED'
            subnets = @($values.SubnetId)
            securityGroups = @($values.SecurityGroupId)
        }
    }
}
$requestPath = Join-Path $PSScriptRoot 'run-task-request.json'
[IO.File]::WriteAllText($requestPath, ($request | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
# This launches a chargeable one-off Fargate task. Read the deployment guide first.
aws ecs run-task --cli-input-json "file://$requestPath" --region $Region
if ($LASTEXITCODE -ne 0) { throw 'RunTask request failed.' }
Write-Output "Check the returned failures array, task stoppedReason/exitCode and CloudWatch log group: $($values.TaskLogs)"
