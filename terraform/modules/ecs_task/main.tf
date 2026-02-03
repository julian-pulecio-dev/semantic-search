resource "aws_cloudwatch_log_group" "ecs_app" {
  name              = "/ecs/${var.name}"
  retention_in_days = 14   # guarda los logs por 14 días (ajusta según necesidad)
}

resource "aws_ecs_task_definition" "app" {
  family                   = var.name
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
      command = var.container_command
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ecs_app.name
          awslogs-region        = "us-east-1"
          awslogs-stream-prefix = "app"
        }
      }
      
      environment = var.environment_variables
    }
  ])

  
}
