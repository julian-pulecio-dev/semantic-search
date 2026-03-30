resource "aws_s3_bucket" "s3_bucket" {
  bucket_prefix = var.name_prefix
  force_destroy = true
}