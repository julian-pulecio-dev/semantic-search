variable "name" {
    description = "A prefix for naming AWS resources"
    type        = string
}

variable "db_name" {
    description = "The name of the database to create in RDS"
    type        = string
}

variable "db_user" {
    description = "The username for the database"
    type        = string
}

variable "db_password" {
    description = "The password for the database"
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

variable "s3_bucket_name" {
    description = "The name of the S3 bucket to use for storing documents"
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