#!/bin/bash

# connect.sh

set -e

CONTAINER_NAME="${1:-app}"

echo "=== 1. Buscando clusters disponibles ==="
CLUSTERS=$(aws ecs list-clusters --query "clusterArns[*]" --output text)

if [ -z "$CLUSTERS" ]; then
  echo "No se encontraron clusters ECS"
  exit 1
fi

IFS=$'\t' read -r -a CLUSTER_LIST <<< "$CLUSTERS"

if [ "${#CLUSTER_LIST[@]}" -eq 1 ]; then
  CLUSTER_ARN="${CLUSTER_LIST[0]}"
else
  echo "Clusters disponibles:"
  for i in "${!CLUSTER_LIST[@]}"; do
    echo "  [$i] ${CLUSTER_LIST[$i]}"
  done
  read -r -p "Selecciona el numero del cluster: " SELECTION
  CLUSTER_ARN="${CLUSTER_LIST[$SELECTION]}"
fi

CLUSTER_NAME="${CLUSTER_ARN##*/}"
echo "Cluster seleccionado: $CLUSTER_NAME"

echo "=== 2. Buscando servicios en el cluster ==="
SERVICES=$(aws ecs list-services --cluster "$CLUSTER_NAME" --query "serviceArns[*]" --output text)

if [ -z "$SERVICES" ]; then
  echo "No se encontraron servicios en el cluster $CLUSTER_NAME"
  exit 1
fi

IFS=$'\t' read -r -a SERVICE_LIST <<< "$SERVICES"

if [ "${#SERVICE_LIST[@]}" -eq 1 ]; then
  SERVICE_ARN="${SERVICE_LIST[0]}"
else
  echo "Servicios disponibles:"
  for i in "${!SERVICE_LIST[@]}"; do
    echo "  [$i] ${SERVICE_LIST[$i]}"
  done
  read -r -p "Selecciona el numero del servicio: " SELECTION
  SERVICE_ARN="${SERVICE_LIST[$SELECTION]}"
fi

SERVICE_NAME="${SERVICE_ARN##*/}"
echo "Servicio seleccionado: $SERVICE_NAME"

echo "=== 3. Obteniendo tarea activa del servicio ==="
TASK_ARN=$(aws ecs list-tasks \
  --cluster "$CLUSTER_NAME" \
  --service-name "$SERVICE_NAME" \
  --query "taskArns[0]" \
  --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
  echo "No hay tareas activas en el servicio $SERVICE_NAME"
  exit 1
fi

echo "Tarea encontrada: $TASK_ARN"

echo "=== 4. Conectando al contenedor ==="
aws ecs execute-command \
  --cluster "$CLUSTER_NAME" \
  --task "$TASK_ARN" \
  --container "$CONTAINER_NAME" \
  --interactive \
  --command "/bin/sh"