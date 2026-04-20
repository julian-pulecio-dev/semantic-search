resource "aws_cloudwatch_log_group" "eventbridge_debug_s3_upload" {
  name =  "eventbridge/debug/s3_upload/${var.name}"
  retention_in_days = 1
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
      object = {
        key = [{
          prefix = "documents/"
        }]
      }
    }
  })
}
