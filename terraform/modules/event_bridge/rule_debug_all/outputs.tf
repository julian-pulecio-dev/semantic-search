output "event_rule_arn" {
  value = aws_cloudwatch_event_rule.debug.arn
}

output "event_rule_name" {
  value = aws_cloudwatch_event_rule.debug.name
}

output "log_group_arn" {
  value = aws_cloudwatch_log_group.eventbridge_debug.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.eventbridge_debug.name
}