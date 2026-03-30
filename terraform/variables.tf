variable "db_name" {
  type = string
}

variable "db_user" {
  type = string
}

variable "db_password" {
  type = string
}

variable "name" {
  type = string
}

variable "ecs_desired_count" {
  type     = number
  default  = null
  nullable = true
}