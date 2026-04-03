# destroy.ps1

param(
  [string]$ClusterName = "semantic-search-doc-chunking-ecs-cluster",
  [string]$ServiceName = "semantic-search-doc-chunking-service",
  [string]$VpcId = "vpc-05f93327ddc007683"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 1. Disabling autoscaling ===" -ForegroundColor Cyan
aws application-autoscaling register-scalable-target `
  --service-namespace ecs `
  --resource-id "service/$ClusterName/$ServiceName" `
  --scalable-dimension "ecs:service:DesiredCount" `
  --min-capacity 0 `
  --max-capacity 0

Write-Host "=== 2. Scaling ECS service down to 0 tasks ===" -ForegroundColor Cyan
aws ecs update-service `
  --cluster $ClusterName `
  --service $ServiceName `
  --desired-count 0

Write-Host "=== 3. Waiting for the service to stabilize ===" -ForegroundColor Cyan
aws ecs wait services-stable `
  --cluster $ClusterName `
  --services $ServiceName

Write-Host "=== 4. Waiting for ECS ENIs to be released ===" -ForegroundColor Cyan
$maxAttempts = 20
$attempt = 0
do {
  Start-Sleep -Seconds 15
  $enis = aws ec2 describe-network-interfaces `
    --filters "Name=vpc-id,Values=$VpcId" "Name=status,Values=in-use" `
    --query "NetworkInterfaces[*].NetworkInterfaceId" `
    --output json | ConvertFrom-Json
  $attempt++
  Write-Host "Attempt $attempt`: $($enis.Count) active ENIs"
} while ($enis.Count -gt 0 -and $attempt -lt $maxAttempts)

Write-Host "=== 5. Releasing EIPs ===" -ForegroundColor Cyan
$addresses = aws ec2 describe-addresses `
  --filters "Name=domain,Values=vpc" `
  --query "Addresses[*].{AllocId:AllocationId,AssocId:AssociationId}" `
  --output json | ConvertFrom-Json

foreach ($addr in $addresses) {
  if ($addr.AssocId) {
    aws ec2 disassociate-address --association-id $addr.AssocId
  }
  aws ec2 release-address --allocation-id $addr.AllocId
}

Write-Host "=== 6. Running terraform destroy ===" -ForegroundColor Cyan
terraform destroy -auto-approve

Write-Host "=== Destroy completed ===" -ForegroundColor Green