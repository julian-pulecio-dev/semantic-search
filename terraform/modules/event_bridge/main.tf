module "evenbridge_rule" {
  source = "./rule"
  name = var.name
  event_source = var.event_source
  detail_type = var.detail_type
  s3_bucket_name = var.s3_bucket_name
  event_prefix = var.event_prefix
}

module "policy_eventbridge_sqs" {
  source = "./policy_eventbridge_sqs"
  sqs_url = var.sqs_queue_url
  sqs_arn = var.sqs_queue_arn
  event_rule_arn = module.evenbridge_rule.event_rule_arn
}

module "target_sqs" {
  source = "./target_sqs"
  target_arn = var.sqs_queue_arn
  target_id = var.sqs_queue_url
  rule_name = module.evenbridge_rule.event_rule_name
  event_rule_arn = module.evenbridge_rule.event_rule_arn
  bucket_dependency = var.s3_bucket_name
  rule_dependency = module.evenbridge_rule
  depends_on = [
    module.evenbridge_rule
  ]
}

module "target_cloudwatch" {
  source = "./target_cloudwatch"
  target_arn = module.evenbridge_rule.log_group_arn
  target_id = module.evenbridge_rule.log_group_name
  rule_name = module.evenbridge_rule.event_rule_name
  event_rule_arn = module.evenbridge_rule.event_rule_arn
  bucket_dependency = var.s3_bucket_name
  rule_dependency = module.evenbridge_rule
  depends_on = [
    module.evenbridge_rule
  ]
}