# createsuperuser.ps1

param(
  [string]$ContainerName = "app"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 1. Looking for available clusters ===" -ForegroundColor Cyan
$Clusters = aws ecs list-clusters --query "clusterArns[*]" --output text
$ClusterList = $Clusters -split "\t"

if ($ClusterList.Count -eq 0) {
  Write-Host "No ECS clusters found" -ForegroundColor Red
  exit 1
}

if ($ClusterList.Count -eq 1) {
  $ClusterArn = $ClusterList[0]
} else {
  Write-Host "Available clusters:"
  for ($i = 0; $i -lt $ClusterList.Count; $i++) {
    Write-Host "  [$i] $($ClusterList[$i])"
  }
  $Selection = Read-Host "Select the cluster number"
  $ClusterArn = $ClusterList[$Selection]
}

$ClusterName = $ClusterArn -replace ".*/" , ""
Write-Host "Selected cluster: $ClusterName" -ForegroundColor Green

Write-Host "=== 2. Looking for services in the cluster ===" -ForegroundColor Cyan
$Services = aws ecs list-services --cluster $ClusterName --query "serviceArns[*]" --output text
$ServiceList = $Services -split "\t"

if ($ServiceList.Count -eq 0) {
  Write-Host "No services found in cluster $ClusterName" -ForegroundColor Red
  exit 1
}

if ($ServiceList.Count -eq 1) {
  $ServiceArn = $ServiceList[0]
} else {
  Write-Host "Available services:"
  for ($i = 0; $i -lt $ServiceList.Count; $i++) {
    Write-Host "  [$i] $($ServiceList[$i])"
  }
  $Selection = Read-Host "Select the service number"
  $ServiceArn = $ServiceList[$Selection]
}

$ServiceName = $ServiceArn -replace ".*/" , ""
Write-Host "Selected service: $ServiceName" -ForegroundColor Green

Write-Host "=== 3. Getting active task for the service ===" -ForegroundColor Cyan
$TaskArn = aws ecs list-tasks `
  --cluster $ClusterName `
  --service-name $ServiceName `
  --query "taskArns[0]" `
  --output text

if ($TaskArn -eq "None" -or -not $TaskArn) {
  Write-Host "No active tasks in service $ServiceName" -ForegroundColor Red
  exit 1
}

Write-Host "Task found: $TaskArn" -ForegroundColor Green

Write-Host "=== 4. Running migrations ===" -ForegroundColor Cyan
aws ecs execute-command `
  --cluster $ClusterName `
  --task $TaskArn `
  --container $ContainerName `
  --interactive `
  --command "python manage.py migrate"

if ($LASTEXITCODE -ne 0) {
  Write-Host "Error running migrations" -ForegroundColor Red
  exit 1
}

Write-Host "Migrations completed" -ForegroundColor Green

Write-Host "=== 5. Creating superuser ===" -ForegroundColor Cyan
aws ecs execute-command `
  --cluster $ClusterName `
  --task $TaskArn `
  --container $ContainerName `
  --interactive `
  --command "python manage.py createsuperuser"