output "name" {
  value = aws_sqs_queue.terraform_queue.name
}

output "arn" {
  value = aws_sqs_queue.terraform_queue.arn
}

output "url" {
  value = aws_sqs_queue.terraform_queue.id
}