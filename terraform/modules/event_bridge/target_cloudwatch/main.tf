resource "aws_cloudwatch_event_target" "cloudwatch_target" {
  rule           = var.rule_name
  event_bus_name = "default"
  arn            = var.target_arn
  depends_on = [
    var.bucket_dependency,
    var.rule_dependency
  ]

}