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

variable "secret_variables" {
  description = "Secrets injected into the container from Secrets Manager (not stored in tfstate)"
  type = list(object({
    name      = string
    valueFrom = string
  }))
  default = []
}

variable "sqs_queue_arn" {
  type = string
}

variable "embedding_sqs_queue_arn" {
  description = "ARN of the embedding SQS queue that this worker sends batches to"
  type        = string
}
