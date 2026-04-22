variable "sqs_url" {
    description = "URL of the SQS queue"
    type        = string
}

variable "sqs_arn" {
    description = "ARN of the SQS queue"
    type        = string
}

variable "event_rule_arn" {
    description = "ARN of the EventBridge rule that will trigger the SQS action"
    type        = string
}