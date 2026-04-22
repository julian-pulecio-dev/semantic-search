data "aws_secretsmanager_secret" "db_password" {
  name = var.db_password_secret_name
}

data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = data.aws_secretsmanager_secret.db_password.id
}

data "aws_secretsmanager_secret" "db_user" {
  name = var.db_user_secret_name
}

data "aws_secretsmanager_secret_version" "db_user" {
  secret_id = data.aws_secretsmanager_secret.db_user.id
}

module "policy_eventbridge_cloudwatch" {
  source = "./modules/policies/policy_eventbridge_cloudwatch"
  name = "${var.name}-eventbridge-cloudwatch-policy"
}

module "s3" {
  source = "./modules/s3"
}

module "sqs_sclicing" {
  source = "./modules/sqs"
  name = "${var.name}-sqs-slicing"
}


module "eventbridge" {
  name = "${var.name}-eventbridge"
  detail_type = ["Object Created"]
  event_prefix = "documents/"
  event_source = ["aws.s3"]
  source = "./modules/event_bridge"
  s3_bucket_name = module.s3.bucket_name
  sqs_queue_arn = module.sqs_sclicing.arn
  sqs_queue_url = module.sqs_sclicing.url
} 

module "vpc" {
  source = "./modules/vpc"
  name = "${var.name}-vpc"
}

module "rds" {
  source = "./modules/rds"
  vpc_id = module.vpc.vpc_id
  db_name     = var.db_name
  db_user     = data.aws_secretsmanager_secret_version.db_user.secret_string
  db_password = data.aws_secretsmanager_secret_version.db_password.secret_string
  subnet_group_name = module.vpc.subnet_group_name
  allowed_security_group_ids = [module.vpc.security_group_id]
}

module "ecs_worker" {
  source = "./modules/ecs_worker"
  name   = "${var.name}-page-slicing-worker"
  sqs_queue_arn = module.sqs_sclicing.arn
  sqs_queue_url = module.sqs_sclicing.url
  sqs_queue_name = module.sqs_sclicing.name
  subnet_ids = module.vpc.subnet_ids
  security_group_id = module.vpc.security_group_id
  db_name = var.db_name
  db_user_secret_arn = data.aws_secretsmanager_secret.db_user.arn
  db_password_secret_arn = data.aws_secretsmanager_secret.db_password.arn
  db_host = module.rds.database_host
  db_port = module.rds.database_port
  s3_bucket_name = module.s3.bucket_name
  desired_count = var.ecs_desired_count
  workers_command = "workers.document_page_slicing.run"
}

# module "ecs_doc_chunking" {
#   source                  = "./modules/ecs_doc_chunking"
#   name                    = "${var.name}-doc-chunking"
#   sqs_queue_arn           = module.sqs.arn
#   sqs_queue_url           = module.sqs.url
#   sqs_queue_name          = module.sqs.name
#   embedding_sqs_queue_arn = module.sqs_embedding.arn
#   embedding_sqs_queue_url = module.sqs_embedding.url
#   s3_bucket_name          = module.s3.bucket_name
#   subnet_ids              = module.vpc.subnet_ids
#   security_group_id       = module.vpc.security_group_id
#   db_name                 = var.db_name
#   db_user_secret_arn      = data.aws_secretsmanager_secret.db_user.arn
#   db_password_secret_arn  = data.aws_secretsmanager_secret.db_password.arn
#   db_host                 = module.rds.database_host
#   db_port                 = module.rds.database_port
#   desired_count           = var.ecs_desired_count
# }

# module "ecs_embedding" {
#   source                 = "./modules/ecs_embedding"
#   name                   = "${var.name}-embedding"
#   sqs_queue_arn          = module.sqs_embedding.arn
#   sqs_queue_url          = module.sqs_embedding.url
#   sqs_queue_name         = module.sqs_embedding.name
#   subnet_ids             = module.vpc.subnet_ids
#   security_group_id      = module.vpc.security_group_id
#   db_name                = var.db_name
#   db_user_secret_arn     = data.aws_secretsmanager_secret.db_user.arn
#   db_password_secret_arn = data.aws_secretsmanager_secret.db_password.arn
#   db_host                = module.rds.database_host
#   db_port                = module.rds.database_port
#   s3_bucket_name         = module.s3.bucket_name
#   desired_count          = var.ecs_desired_count
# }

module "ecs_web" {
  source                 = "./modules/ecs_web"
  name                   = "${var.name}-ecs"
  vpc_id                 = module.vpc.vpc_id
  db_name                = var.db_name
  db_user_secret_arn     = data.aws_secretsmanager_secret.db_user.arn
  db_password_secret_arn = data.aws_secretsmanager_secret.db_password.arn
  db_host                = module.rds.database_host
  db_port                = module.rds.database_port
  s3_bucket_name         = module.s3.bucket_name
  subnet_ids             = module.vpc.subnet_ids
  security_group_id      = module.vpc.security_group_id
  desired_count          = var.ecs_desired_count
}
