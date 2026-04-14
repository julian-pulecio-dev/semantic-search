variable "name" {
  type = string
}

variable "iam_role_arn" {
  type = string
}

variable "sqs_queue_arn" {
  type = string
}

variable "environment_variables" {
  type = list(object({
    name  = string
    value = string
  }))
}

variable "secret_variables" {
  description = "Secrets injected into the container from Secrets Manager"
  type = list(object({
    name      = string
    valueFrom = string
  }))
  default = []
}
