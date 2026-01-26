resource "aws_ecs_task_definition" "app" {
  family                   = "dockerhub-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"

  execution_role_arn = var.iam_role_arn

  container_definitions = jsonencode([
    {
      name      = "app"
      image     = "julianpuleciodev/semantic-search"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]
    }
  ])
}
