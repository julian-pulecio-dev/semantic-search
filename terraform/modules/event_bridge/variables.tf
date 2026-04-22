variable "name" {
  description = "The name of the EventBridge rule."
  type        = string
  
}

variable s3_bucket_name {
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

variable "event_source" {
  description = "The source of the events to match."
  type        = list(string)
}

variable "detail_type" {
  description = "The detail type of the events to match."
  type        = list(string)
}

variable "event_prefix" {
  description = "The prefix of the S3 object key to match."
  type        = string
}