variable "db_name" {
  type = string
}

variable "db_user_secret_name" {
  description = "Name of the AWS Secrets Manager secret that holds the DB username"
  type        = string
}

variable "db_password_secret_name" {
  description = "Name of the AWS Secrets Manager secret that holds the DB password"
  type        = string
}

variable "name" {
  type = string
}

variable "ecs_desired_count" {
  type     = number
  default  = null
  nullable = true
}