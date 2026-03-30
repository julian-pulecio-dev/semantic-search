module "s3" {
  source = "./modules/s3"
}

module "sqs" {
  source = "./modules/sqs"
  name = "${var.name}-sqs"
}

module "eventbridge" {
  source = "./modules/event_bridge"
  bucket_name = module.s3.bucket_name
  sqs_queue_arn = module.sqs.arn
  sqs_queue_url = module.sqs.url
} 

module "vpc" {
  source = "./modules/vpc"
  name = "${var.name}-vpc"
}

module "rds" {
  source = "./modules/rds"
  vpc_id = module.vpc.vpc_id
  db_name = var.db_name
  db_user = var.db_user
  db_password = var.db_password
  subnet_group_name = module.vpc.subnet_group_name
  allowed_security_group_ids = [module.vpc.security_group_id]
}

module "ecs_doc_chunking" {
  source              = "./modules/ecs_doc_chunking"
  name                = "${var.name}-doc-chunking"
  sqs_queue_arn       = module.sqs.arn
  sqs_queue_url       = module.sqs.url
  sqs_queue_name      = module.sqs.name
  s3_bucket_name      = module.s3.bucket_name
  subnet_ids          = module.vpc.subnet_ids
  security_group_id   = module.vpc.security_group_id
  db_name             = var.db_name
  db_user             = var.db_user
  db_password         = var.db_password
  db_host             = module.rds.database_host
  db_port             = module.rds.database_port
  desired_count       = var.ecs_desired_count
}

module "ecs_web" {
  source            = "./modules/ecs_web"
  name              = "${var.name}-ecs"
  db_name           = var.db_name
  db_user           = var.db_user
  db_password       = var.db_password
  db_host           = module.rds.database_host
  db_port           = module.rds.database_port
  s3_bucket_name    = module.s3.bucket_name
  subnet_ids        = module.vpc.subnet_ids
  security_group_id = module.vpc.security_group_id
  desired_count     = var.ecs_desired_count
}
