module "ecs_cluster" {
  source = "./cluster"
  name = "${var.name}-ecs-cluster"
}

module "iam_role" {
  source = "./iam_role"
  name = "${var.name}-ecsTaskExecutionRole-dockerhub"
}

module "ecs_task_definition" {
  name = "${var.name}-ecs-task-definition-app"
  source = "./task"
  iam_role_arn = module.iam_role.arn
  environment_variables = [
    {
      name  = "DB_HOST"
      value = var.db_host
    },
    {
      name  = "DB_NAME"
      value = var.db_name
    },
    {
      name  = "DB_USER"
      value = var.db_user
    },
    {
      name  = "DB_PASSWORD"
      value = var.db_password
    },
    {
      name  = "DB_PORT"
      value = var.db_port
    },
    {
      name  = "S3_BUCKET_NAME"
      value = var.s3_bucket_name
    }
  ]
  container_command = []
  s3_bucket_name = var.s3_bucket_name
}

module "ecs_task_definition_migrate" {
  name = "${var.name}-ecs-task-definition-migrate"
  source = "./task"
  iam_role_arn = module.iam_role.arn
  environment_variables = [
    {
      name  = "DB_HOST"
      value = var.db_host
    },
    {
      name  = "DB_NAME"
      value = var.db_name
    },
    {
      name  = "DB_USER"
      value = var.db_user
    },
    {
      name  = "DB_PASSWORD"
      value = var.db_password
    },
    {
      name  = "DB_PORT"
      value = var.db_port
    },
    {
      name  = "S3_BUCKET_NAME"
      value = var.s3_bucket_name
    }
  ]
  container_command = ["python", "manage.py", "migrate", "--noinput"]
  s3_bucket_name = var.s3_bucket_name
}

module "ecs_service" {
  source = "./service"
  name = "${var.name}-ecs-service"
  cluster_arn = module.ecs_cluster.arn
  task_definition_arn = module.ecs_task_definition.arn
  desired_count = 2
  vpc_subnets_ids = var.subnet_ids
  vpc_security_group_id = var.security_group_id
}