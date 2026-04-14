variable "name" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "service_name" {
  type = string
}

variable "sqs_queue_name" {
  description = "Name of the embedding SQS queue (used for CloudWatch alarms)"
  type        = string
}

variable "max_capacity" {
  type    = number
  default = 5
}

variable "scale_out_threshold" {
  description = "Total messages that trigger adding a task"
  type        = number
  default     = 5
}
