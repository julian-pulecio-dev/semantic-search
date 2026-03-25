output "ecs_cluster_name" {
  value = module.ecs_cluster.name
}

output "ecs_service_name" {
  value = module.ecs_service.name
}

output "migration_task_definition" {
  value = module.ecs_task_definition_migrate.arn
}