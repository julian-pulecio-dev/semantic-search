variable "name" {
  type = string
}

variable "iam_role_arn" {
  type = string
}

variable "environment_variables" {
  type = list(object({
    name  = string
    value = string
  }))
}

variable "s3_bucket_name" {
  type = string
}

variable "sqs_queue_arn" {
  type = string
}
