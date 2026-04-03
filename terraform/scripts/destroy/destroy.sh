#!/bin/bash

# destroy.sh

set -e

CLUSTER_NAME="${1:-semantic-search-doc-chunking-ecs-cluster}"
SERVICE_NAME="${2:-semantic-search-doc-chunking-service}"
VPC_ID="${3:-vpc-05f93327ddc007683}"

echo "=== 1. Disabling autoscaling ==="
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id "service/$CLUSTER_NAME/$SERVICE_NAME" \
  --scalable-dimension "ecs:service:DesiredCount" \
  --min-capacity 0 \
  --max-capacity 0

echo "=== 2. Scaling ECS service down to 0 tasks ==="
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$SERVICE_NAME" \
  --desired-count 0

echo "=== 3. Waiting for the service to stabilize ==="
aws ecs wait services-stable \
  --cluster "$CLUSTER_NAME" \
  --services "$SERVICE_NAME"

echo "=== 4. Waiting for ECS ENIs to be released ==="
MAX_ATTEMPTS=20
ATTEMPT=0
while true; do
  ENIS=$(aws ec2 describe-network-interfaces \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=status,Values=in-use" \
    --query "NetworkInterfaces[*].NetworkInterfaceId" \
    --output text)

  ATTEMPT=$((ATTEMPT + 1))

  if [ -z "$ENIS" ]; then
    echo "Attempt $ATTEMPT: 0 active ENIs"
    break
  fi

  ENI_COUNT=$(echo "$ENIS" | wc -w | tr -d ' ')
  echo "Attempt $ATTEMPT: $ENI_COUNT active ENIs"

  if [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
    echo "Timeout waiting for ENIs, continuing anyway..."
    break
  fi

  sleep 15
done

echo "=== 5. Releasing EIPs ==="
# --output text returns tab-separated columns: AssocId\tAllocId
# If AssocId is None, the AWS CLI returns "None" as a string
aws ec2 describe-addresses \
  --filters "Name=domain,Values=vpc" \
  --query "Addresses[*].[AssociationId,AllocationId]" \
  --output text | while IFS=$'\t' read -r ASSOC_ID ALLOC_ID; do

  if [ "$ASSOC_ID" != "None" ] && [ -n "$ASSOC_ID" ]; then
    echo "Disassociating EIP $ASSOC_ID..."
    aws ec2 disassociate-address --association-id "$ASSOC_ID"
  fi

  echo "Releasing EIP $ALLOC_ID..."
  aws ec2 release-address --allocation-id "$ALLOC_ID"
done

echo "=== 6. Running terraform destroy ==="
terraform destroy -auto-approve

echo "=== Destroy completed ==="