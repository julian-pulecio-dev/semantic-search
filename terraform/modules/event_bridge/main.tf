module "eventbridge_s3_notification" {
  source = "./eventbridge_s3_notification"
  name = "s3-document-uploaded-event"
  s3_bucket_name = var.bucket_name
}

module "eventbridge_target" {
  source = "./eventbridge_target"
  target_arn = var.sqs_queue_arn
  target_id = var.sqs_queue_url
  rule_name = module.eventbridge_s3_notification.event_rule_name
  event_rule_arn = module.eventbridge_s3_notification.event_rule_arn
  bucket_dependency = var.bucket_name
  depends_on = [
    module.eventbridge_s3_notification
  ]
}