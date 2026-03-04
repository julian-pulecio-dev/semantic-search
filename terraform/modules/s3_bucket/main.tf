resource "aws_s3_bucket" "s3_bucket" {
  bucket_prefix = var.name_prefix

  tags = {
    Name        = "semantic-search-bucket"
    Environment = "Dev"
  }
}

resource "aws_s3_bucket_policy" "s3_bucket_policy" {
  bucket = aws_s3_bucket.s3_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowPresignedPostUploads"
        Effect    = "Allow"
        Principal = {
          "AWS": "arn:aws:iam::686255988152:user/julianpulecio"
        }
        Action    = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource  = "${aws_s3_bucket.s3_bucket.arn}/*"
      }
    ]
  })
}