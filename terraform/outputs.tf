output "ecs_cluster_name" {
  value = module.ecs_cluster.name
}

output "ecs_service_name" {
  value = module.ecs_service.name
}

output "migration_task_definition" {
  value = module.ecs_task_definition_migrate.arn
}

output "public_subnets" {
  value = module.vpc_subnets.subnet_ids
}

output "ecs_security_group" {
  value = module.vpc_security_group.security_group_id
}