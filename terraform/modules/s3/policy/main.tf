resource "aws_s3_bucket_policy" "s3_bucket_policy" {
  bucket = var.s3_bucket_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowPresignedPostUploads"
        Effect    = "Allow"
        Principal = "*"
        Action    = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource  = "${var.s3_bucket_arn}/*"
      },
      {
        Sid       = "AllowPublicDocumentRead"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${var.s3_bucket_arn}/documents/*"
      }
    ]
  })
}