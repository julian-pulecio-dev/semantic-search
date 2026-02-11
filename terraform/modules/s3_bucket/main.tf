resource "aws_s3_bucket" "s3_bucket" {
  bucket_prefix = var.name_prefix
  tags = {
    Name        = "semantic-search-bucket"
    Environment = "Dev"
  }
}