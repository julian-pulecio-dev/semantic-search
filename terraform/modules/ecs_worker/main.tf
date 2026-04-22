module "ecs_cluster" {
  source = "./cluster"
  name   = "${var.name}-ecs-cluster"
}

module "iam_role" {
  source                 = "./iam_role"
  name                   = "${var.name}-ecsTaskExecutionRole"
  db_password_secret_arn = var.db_password_secret_arn
  db_user_secret_arn     = var.db_user_secret_arn
}

module "ecs_task_definition" {
  source                  = "./task"
  name                    = "${var.name}-ecs-task-definition"
  iam_role_arn            = module.iam_role.arn
  s3_bucket_name          = var.s3_bucket_name
  sqs_queue_arn           = var.sqs_queue_arn
  workers_command         = var.workers_command
  
  environment_variables = [
    { name = "SQS_QUEUE_URL",          value = var.sqs_queue_url },
    { name = "DB_HOST",                value = var.db_host },
    { name = "DB_NAME",                value = var.db_name },
    { name = "DB_PORT",                value = var.db_port },
    { name = "S3_BUCKET_NAME",         value = var.s3_bucket_name },
  ]
  secret_variables = [
    { name = "DB_USER",     valueFrom = var.db_user_secret_arn },
    { name = "DB_PASSWORD", valueFrom = var.db_password_secret_arn }
  ]

}

module "service" {
  source              = "./service"
  name                = "${var.name}-service"
  cluster_arn         = module.ecs_cluster.arn
  task_definition_arn = module.ecs_task_definition.arn
  subnet_ids          = var.subnet_ids
  security_group_id   = var.security_group_id
  desired_count       = coalesce(var.desired_count, 1)
}

module "autoscaling" {
  source              = "./autoscaling"
  name                = var.name
  cluster_name        = module.ecs_cluster.name
  service_name        = module.service.name
  sqs_queue_name      = var.sqs_queue_name
  max_capacity        = var.max_capacity
  scale_out_threshold = var.scale_out_threshold
}
