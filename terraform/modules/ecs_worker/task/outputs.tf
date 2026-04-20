output "arn" {
  value = aws_ecs_task_definition.page_slicing.arn
}

output "task_role_arn" {
  value = aws_iam_role.ecs_task.arn
}
