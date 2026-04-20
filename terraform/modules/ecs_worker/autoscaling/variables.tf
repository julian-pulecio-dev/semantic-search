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
  type = string
}

variable "max_capacity" {
  type    = number
  default = 5
}

variable "scale_out_threshold" {
  description = "Total messages (visible + in-flight) that triggers adding a task"
  type        = number
  default     = 5
}
