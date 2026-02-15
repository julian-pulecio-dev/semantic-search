module "s3_bucket" {
  source = "./modules/s3_bucket"
  name_prefix = "semantic-search-bucket"
}

module "vpc" {
  source = "./modules/vpc"
}

module "vpc_subnets" {
  source = "./modules/vpc_subnets"
  vpc_id = module.vpc.id
  vpc_cidr_block = module.vpc.cidr_block
}

module "vpc_internet_gateway" {
  source = "./modules/vpc_internet_gateway"
  vpc_id = module.vpc.id
}

module "vpc_route_table" {
  source = "./modules/vpc_route_table"
  vpc_id = module.vpc.id
  igw_id = module.vpc_internet_gateway.id
  subnet_ids = module.vpc_subnets.subnet_ids
}

module "vpc_security_group" {
  source = "./modules/iam_security_group"
  name   = "ecs-security-group"
  vpc_id = module.vpc.id
  from_port = 8000
  to_port = 8000
}

module "rds_security_group" {
  source = "./modules/iam_security_group"
  name   = "rds-security-group"
  vpc_id = module.vpc.id
  from_port = 5432
  to_port = 5432
  allowed_security_group_ids = [module.vpc_security_group.security_group_id]
}

module "rds_database" {
  source = "./modules/rds_database"
  name = var.db_name
  db_user = var.db_user
  db_password = var.db_password
  db_instance_class = "db.t3.micro"
  db_subnet_group_name = module.vpc_subnets.subnet_group_name
  security_group_id = module.rds_security_group.security_group_id
}

module "ecs_cluster" {
  source = "./modules/ecs_cluster"
  name = "ecs-cluster"
}

module "iam_role" {
  source = "./modules/iam_role"
  name = "ecsTaskExecutionRole-dockerhub"
}

module "ecs_task_definition" {
  name = "ecs-task-definition-app"
  source = "./modules/ecs_task"
  iam_role_arn = module.iam_role.arn
  environment_variables = [
    {
      name  = "DB_HOST"
      value = module.rds_database.host
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
      value = module.rds_database.port
    },
    {
      name  = "S3_BUCKET_NAME"
      value = module.s3_bucket.name
    }
  ]
  container_command = []
  s3_bucket_name = module.s3_bucket.name
}

module "ecs_task_definition_migrate" {
  name = "ecs-task-definition-migrate"
  source = "./modules/ecs_task"
  iam_role_arn = module.iam_role.arn
  environment_variables = [
    {
      name  = "DB_HOST"
      value = module.rds_database.host
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
      value = module.rds_database.port
    },
    {
      name  = "S3_BUCKET_NAME"
      value = module.s3_bucket.name
    }
  ]
  container_command = ["python", "manage.py", "migrate", "--noinput"]
  s3_bucket_name = module.s3_bucket.name
}

module "ecs_service" {
  source = "./modules/ecs_service"
  name = "dockerhub-ecs-service"
  cluster_arn = module.ecs_cluster.arn
  task_definition_arn = module.ecs_task_definition.arn
  desired_count = 2
  vpc_subnets_ids = module.vpc_subnets.subnet_ids
  vpc_security_group_id = module.vpc_security_group.security_group_id
}