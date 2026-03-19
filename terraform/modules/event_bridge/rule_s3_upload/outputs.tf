output "event_rule_name" {
  value = aws_cloudwatch_event_rule.document_uploaded.name
}

output "event_rule_arn" {
  value = aws_cloudwatch_event_rule.document_uploaded.arn
}

output "log_group_arn" {
  value = aws_cloudwatch_log_group.eventbridge_debug_s3_upload.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.eventbridge_debug_s3_upload.name
}