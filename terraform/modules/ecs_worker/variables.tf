variable "name" {
  description = "A prefix for naming AWS resources"
  type        = string
}

variable "s3_bucket_name" {
  description = "The name of the S3 bucket"
  type        = string
}

variable "subnet_ids" {
  description = "A list of subnet IDs for the ECS tasks"
  type        = list(string)
}

variable "security_group_id" {
  description = "The security group ID for the ECS tasks"
  type        = string
}

variable "db_name" {
  description = "The name of the database"
  type        = string
}

variable "db_user_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the DB username"
  type        = string
}

variable "db_password_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the DB password"
  type        = string
}

variable "db_host" {
  description = "The hostname of the database"
  type        = string
}

variable "db_port" {
  description = "The port of the database"
  type        = string
}

variable "sqs_queue_name" {
  description = "The name of the SQS queue (used for CloudWatch autoscaling alarms)"
  type        = string
}

variable "sqs_queue_arn" {
  description = "ARN of the SQS queue to send batches to"
  type        = string
}

variable "sqs_queue_url" {
  description = "URL of the SQS queue to send batches to"
  type        = string
}

variable "max_capacity" {
  description = "Maximum number of ECS tasks the service can scale out to"
  type        = number
  default     = 5
}

variable "scale_out_threshold" {
  description = "Total messages (visible + in-flight) that triggers adding a task"
  type        = number
  default     = 5
}

variable "desired_count" {
  description = "Number of ECS tasks to run. Set to 0 before destroy."
  type        = number
  default     = null
  nullable    = true
}

variable "workers_command" {
  description = "The command to run in the ECS worker container"
  type        = string
}