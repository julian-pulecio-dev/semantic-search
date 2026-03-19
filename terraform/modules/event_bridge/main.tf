module "notification_s3" {
  source = "./notification_s3"
  s3_bucket_name = var.bucket_name
}

module "policy_cloudwatch" {
  source = "./policy_cloudwatch"
  name = "event-bridge-cloudwatch-policy"
}


module "rule_debug_all" {
  source = "./rule_debug_all"
  name = "event-bridge-debug-all"
  s3_bucket_name = var.bucket_name
}

module "rule_s3_upload" {
  source = "./rule_s3_upload"
  name = "event-bridge-s3-upload"
  s3_bucket_name = var.bucket_name
}


module "policy_sqs" {
  source = "./policy_sqs"
  sqs_url = var.sqs_queue_url
  sqs_arn = var.sqs_queue_arn
  event_rule_arn = module.rule_s3_upload.event_rule_arn
}

module "target_sqs" {
  source = "./target_sqs"
  target_arn = var.sqs_queue_arn
  target_id = var.sqs_queue_url
  rule_name = module.rule_s3_upload.event_rule_name
  event_rule_arn = module.rule_s3_upload.event_rule_arn
  bucket_dependency = var.bucket_name
  rule_dependency = module.rule_s3_upload
  depends_on = [
    module.rule_s3_upload
  ]
}

module "target_debug_s3_upload" {
  source = "./target_cloudwatch"
  target_arn = module.rule_s3_upload.log_group_arn
  target_id = module.rule_s3_upload.log_group_name
  rule_name = module.rule_s3_upload.event_rule_name
  event_rule_arn = module.rule_s3_upload.event_rule_arn
  bucket_dependency = var.bucket_name
  rule_dependency = module.rule_s3_upload
  depends_on = [
    module.rule_s3_upload
  ]
}

module "target_debug_all" {
  source = "./target_cloudwatch"
  target_arn = module.rule_debug_all.log_group_arn
  target_id = module.rule_debug_all.log_group_name
  rule_name = module.rule_debug_all.event_rule_name
  event_rule_arn = module.rule_debug_all.event_rule_arn
  bucket_dependency = var.bucket_name
  rule_dependency = module.rule_debug_all
  depends_on = [
    module.rule_debug_all
  ]
}