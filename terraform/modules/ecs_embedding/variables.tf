variable "name" {
  description = "Prefix for naming AWS resources"
  type        = string
}

variable "sqs_queue_arn" {
  description = "ARN of the embedding SQS queue to consume messages from"
  type        = string
}

variable "sqs_queue_url" {
  description = "URL of the embedding SQS queue"
  type        = string
}

variable "sqs_queue_name" {
  description = "Name of the embedding SQS queue (used for CloudWatch autoscaling alarms)"
  type        = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "db_name" {
  type = string
}

variable "db_user_secret_arn" {
  type = string
}

variable "db_password_secret_arn" {
  type = string
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type = string
}

variable "max_capacity" {
  description = "Maximum number of ECS tasks the service can scale out to"
  type        = number
  default     = 5
}

variable "scale_out_threshold" {
  description = "Total messages that trigger adding a task"
  type        = number
  default     = 5
}

variable "desired_count" {
  description = "Number of ECS tasks to run. Set to 0 before destroy."
  type        = number
  default     = null
  nullable    = true
}
