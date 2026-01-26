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
  source = "./modules/vpc_security_group"
  name   = "ecs-security-group"
  vpc_id = module.vpc.id
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
  source = "./modules/ecs_task"
  iam_role_arn = module.iam_role.arn
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