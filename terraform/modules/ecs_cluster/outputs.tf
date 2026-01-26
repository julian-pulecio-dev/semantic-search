output "arn" {
  value = aws_ecs_cluster.ecs_cluster.arn
}

output "tags" {
  value = aws_ecs_cluster.ecs_cluster.tags
}