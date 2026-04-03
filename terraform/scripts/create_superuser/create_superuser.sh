#!/bin/bash

# createsuperuser.sh

set -e

CONTAINER_NAME="${1:-app}"

echo "=== 1. Looking for available clusters ==="
CLUSTERS=$(aws ecs list-clusters --query "clusterArns[*]" --output text)

if [ -z "$CLUSTERS" ]; then
  echo "No ECS clusters found"
  exit 1
fi

# Convert output into an array
IFS=$'\t' read -r -a CLUSTER_LIST <<< "$CLUSTERS"

if [ "${#CLUSTER_LIST[@]}" -eq 1 ]; then
  CLUSTER_ARN="${CLUSTER_LIST[0]}"
else
  echo "Available clusters:"
  for i in "${!CLUSTER_LIST[@]}"; do
    echo "  [$i] ${CLUSTER_LIST[$i]}"
  done
  read -r -p "Select the cluster number: " SELECTION
  CLUSTER_ARN="${CLUSTER_LIST[$SELECTION]}"
fi

CLUSTER_NAME="${CLUSTER_ARN##*/}"
echo "Selected cluster: $CLUSTER_NAME"

echo "=== 2. Looking for services in the cluster ==="
SERVICES=$(aws ecs list-services --cluster "$CLUSTER_NAME" --query "serviceArns[*]" --output text)

if [ -z "$SERVICES" ]; then
  echo "No services found in cluster $CLUSTER_NAME"
  exit 1
fi

IFS=$'\t' read -r -a SERVICE_LIST <<< "$SERVICES"

if [ "${#SERVICE_LIST[@]}" -eq 1 ]; then
  SERVICE_ARN="${SERVICE_LIST[0]}"
else
  echo "Available services:"
  for i in "${!SERVICE_LIST[@]}"; do
    echo "  [$i] ${SERVICE_LIST[$i]}"
  done
  read -r -p "Select the service number: " SELECTION
  SERVICE_ARN="${SERVICE_LIST[$SELECTION]}"
fi

SERVICE_NAME="${SERVICE_ARN##*/}"
echo "Selected service: $SERVICE_NAME"

echo "=== 3. Getting active task for the service ==="
TASK_ARN=$(aws ecs list-tasks \
  --cluster "$CLUSTER_NAME" \
  --service-name "$SERVICE_NAME" \
  --query "taskArns[0]" \
  --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
  echo "No active tasks in service $SERVICE_NAME"
  exit 1
fi

echo "Task found: $TASK_ARN"

echo "=== 4. Opening session in the container ==="
aws ecs execute-command \
  --cluster "$CLUSTER_NAME" \
  --task "$TASK_ARN" \
  --container "$CONTAINER_NAME" \
  --interactive \
  --command "python manage.py createsuperuser"