output "ecs_cluster_name" {
  value = module.ecs.ecs_cluster_name
}

output "ecs_service_name" {
  value = module.ecs.ecs_service_name
}

output "migration_task_definition" {
  value = module.ecs.migration_task_definition
}

output "public_subnets" {
  value = module.vpc.subnet_ids
}

output "ecs_security_group" {
  value = module.vpc.security_group_id
}

output "s3_bucket_name" {
  value = module.s3.bucket_name
}