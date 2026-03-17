resource "aws_s3_bucket_policy" "s3_bucket_policy" {
  bucket = var.s3_bucket_name

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
        Resource  = "${var.s3_bucket_arn}/*"
      }
    ]
  })
}