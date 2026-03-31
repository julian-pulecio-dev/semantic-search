#!/bin/bash

# destroy.sh

set -e

CLUSTER_NAME="${1:-semantic-search-doc-chunking-ecs-cluster}"
SERVICE_NAME="${2:-semantic-search-doc-chunking-service}"
VPC_ID="${3:-vpc-05f93327ddc007683}"

echo "=== 1. Desactivando autoscaling ==="
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id "service/$CLUSTER_NAME/$SERVICE_NAME" \
  --scalable-dimension "ecs:service:DesiredCount" \
  --min-capacity 0 \
  --max-capacity 0

echo "=== 2. Bajando servicio ECS a 0 tareas ==="
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$SERVICE_NAME" \
  --desired-count 0

echo "=== 3. Esperando que el servicio estabilice ==="
aws ecs wait services-stable \
  --cluster "$CLUSTER_NAME" \
  --services "$SERVICE_NAME"

echo "=== 4. Esperando que las ENIs de ECS se liberen ==="
MAX_ATTEMPTS=20
ATTEMPT=0
while true; do
  ENIS=$(aws ec2 describe-network-interfaces \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=status,Values=in-use" \
    --query "NetworkInterfaces[*].NetworkInterfaceId" \
    --output text)

  ATTEMPT=$((ATTEMPT + 1))

  if [ -z "$ENIS" ]; then
    echo "Intento $ATTEMPT: 0 ENIs activas"
    break
  fi

  ENI_COUNT=$(echo "$ENIS" | wc -w | tr -d ' ')
  echo "Intento $ATTEMPT: $ENI_COUNT ENIs activas"

  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
    echo "Timeout esperando ENIs, continuando de todas formas..."
    break
  fi

  sleep 15
done

echo "=== 5. Liberando EIPs ==="
# --output text devuelve columnas separadas por tabs: AssocId\tAllocId
# Si AssocId es None, AWS CLI devuelve "None" como string
aws ec2 describe-addresses \
  --filters "Name=domain,Values=vpc" \
  --query "Addresses[*].[AssociationId,AllocationId]" \
  --output text | while IFS=$'\t' read -r ASSOC_ID ALLOC_ID; do

  if [ "$ASSOC_ID" != "None" ] && [ -n "$ASSOC_ID" ]; then
    echo "Desasociando EIP $ASSOC_ID..."
    aws ec2 disassociate-address --association-id "$ASSOC_ID"
  fi

  echo "Liberando EIP $ALLOC_ID..."
  aws ec2 release-address --allocation-id "$ALLOC_ID"
done

echo "=== 6. Corriendo terraform destroy ==="
terraform destroy -auto-approve

echo "=== Destroy completado ==="