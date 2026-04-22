resource "aws_cloudwatch_event_rule" "rule" {
  name           = "${var.name}-rule"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source = var.event_source
    "detail-type" = var.detail_type
    detail = {
      bucket = {
        name = [var.s3_bucket_name]
      }
      object = {
        key = [{
          prefix = var.event_prefix
        }]
      }
    }
  })
}

resource "aws_cloudwatch_log_group" "eventbridge_rule_logs" {
  name =  "eventbridge/debug/${var.name}"
  retention_in_days = 1
}

resource "aws_iam_role" "eventbridge_logs_role" {
  name = "${var.name}-eventbridge-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}