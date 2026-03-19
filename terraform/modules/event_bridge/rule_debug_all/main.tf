resource "aws_cloudwatch_event_rule" "debug" {
  name           = "${var.name}-debug"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source = ["aws.s3"]
    detail = {
      bucket = {
        name = [var.s3_bucket_name]
      }
    }
  })
}

resource "aws_cloudwatch_log_group" "eventbridge_debug" {
  name =  "eventbridge/debug/all/${var.name}"
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