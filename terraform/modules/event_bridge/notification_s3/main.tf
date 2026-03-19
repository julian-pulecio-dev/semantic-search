resource "aws_s3_bucket_notification" "eventbridge" {
  bucket      = var.s3_bucket_name
  eventbridge = true
}