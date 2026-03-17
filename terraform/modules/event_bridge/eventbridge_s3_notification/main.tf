resource "aws_s3_bucket_notification" "eventbridge" {
  bucket      = var.s3_bucket_name
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "document_uploaded" {
  name           = var.name
  event_bus_name = "default"

  event_pattern = jsonencode({
    source = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = {
        name = [var.s3_bucket_name]
      }
    }
  })
}

resource "aws_cloudwatch_event_rule" "debug_all" {
  name           = "debug-all-events"
  event_bus_name = "default"

  event_pattern = jsonencode({
    source = [{
      exists = true
    }]
  })
}

resource "aws_cloudwatch_log_group" "eventbridge_debug_all" {
  name =  "${var.name}/eventbridge/debug/all"
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