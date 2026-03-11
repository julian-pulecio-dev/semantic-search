resource "aws_cloudwatch_event_target" "sqs_target" {
  rule           = var.rule_name
  event_bus_name = var.event_bus_name
  arn            = var.target_arn

  input_transformer {
    input_paths = {
      bucket = "$.detail.bucket.name"
      key    = "$.detail.object.key"
    }

    input_template = <<EOF
      {
        "bucket": <bucket>,
        "key": <key>
      }
      EOF
  }
}