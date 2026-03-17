variable bucket_name {
  description = "The name of the S3 bucket to store EventBridge logs."
  type        = string
}

variable "sqs_queue_arn" {
  description = "The ARN of the SQS queue to send EventBridge events to."
  type        = string
}

variable "sqs_queue_url" {
  description = "The URL of the SQS queue to send EventBridge events to."
  type        = string
}
