variable "name_prefix" {
  description = "The prefix for the S3 bucket name"
  type        = string
}

variable "cors_allowed_origins" {
  description = "List of origins allowed to make cross-origin requests to the bucket"
  type        = list(string)
  default     = ["*"]
}