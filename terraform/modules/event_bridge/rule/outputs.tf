output "event_rule_arn" {
  value = aws_cloudwatch_event_rule.rule.arn
}

output "event_rule_name" {
  value = aws_cloudwatch_event_rule.rule.name
}

output "log_group_arn" {
  value = aws_cloudwatch_log_group.eventbridge_rule_logs.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.eventbridge_rule_logs.name
}