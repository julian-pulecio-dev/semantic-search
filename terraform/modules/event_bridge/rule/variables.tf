variable "s3_bucket_name" {
  type = string
}

variable "name" {
    description = "The name prefix for the resources created by this module."
    type        = string
}

variable "event_prefix" {
  type    = string
  default = "documents/"
}

variable "detail_type" {
  type = list(string)
}

variable "event_source" {
  type = list(string)
}