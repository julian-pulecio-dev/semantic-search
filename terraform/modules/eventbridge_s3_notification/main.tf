resource "aws_s3_bucket_notification" "eventbridge" {
  bucket = var.s3_bucket_id
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "document_uploaded" {
  name           = var.name
  event_bus_name = var.event_bus_name

  event_pattern = jsonencode({
    "source": ["aws.s3"],
    "detail-type": ["Object Created"],
    "detail": {
      "bucket": {
        "name": [var.s3_bucket_id]
      }
    }
  })
}