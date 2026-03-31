# connect.ps1

param(
  [string]$ContainerName = "app"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 1. Buscando clusters disponibles ===" -ForegroundColor Cyan
$Clusters = aws ecs list-clusters --query "clusterArns[*]" --output text
$ClusterList = $Clusters -split "\t"

if ($ClusterList.Count -eq 0) {
  Write-Host "No se encontraron clusters ECS" -ForegroundColor Red
  exit 1
}

if ($ClusterList.Count -eq 1) {
  $ClusterArn = $ClusterList[0]
} else {
  Write-Host "Clusters disponibles:"
  for ($i = 0; $i -lt $ClusterList.Count; $i++) {
    Write-Host "  [$i] $($ClusterList[$i])"
  }
  $Selection = Read-Host "Selecciona el numero del cluster"
  $ClusterArn = $ClusterList[$Selection]
}

$ClusterName = $ClusterArn -replace ".*/" , ""
Write-Host "Cluster seleccionado: $ClusterName" -ForegroundColor Green

Write-Host "=== 2. Buscando servicios en el cluster ===" -ForegroundColor Cyan
$Services = aws ecs list-services --cluster $ClusterName --query "serviceArns[*]" --output text
$ServiceList = $Services -split "\t"

if ($ServiceList.Count -eq 0) {
  Write-Host "No se encontraron servicios en el cluster $ClusterName" -ForegroundColor Red
  exit 1
}

if ($ServiceList.Count -eq 1) {
  $ServiceArn = $ServiceList[0]
} else {
  Write-Host "Servicios disponibles:"
  for ($i = 0; $i -lt $ServiceList.Count; $i++) {
    Write-Host "  [$i] $($ServiceList[$i])"
  }
  $Selection = Read-Host "Selecciona el numero del servicio"
  $ServiceArn = $ServiceList[$Selection]
}

$ServiceName = $ServiceArn -replace ".*/" , ""
Write-Host "Servicio seleccionado: $ServiceName" -ForegroundColor Green

Write-Host "=== 3. Obteniendo tarea activa del servicio ===" -ForegroundColor Cyan
$TaskArn = aws ecs list-tasks `
  --cluster $ClusterName `
  --service-name $ServiceName `
  --query "taskArns[0]" `
  --output text

if ($TaskArn -eq "None" -or -not $TaskArn) {
  Write-Host "No hay tareas activas en el servicio $ServiceName" -ForegroundColor Red
  exit 1
}

Write-Host "Tarea encontrada: $TaskArn" -ForegroundColor Green

Write-Host "=== 4. Conectando al contenedor ===" -ForegroundColor Cyan
aws ecs execute-command `
  --cluster $ClusterName `
  --task $TaskArn `
  --container $ContainerName `
  --interactive `
  --command "/bin/sh"