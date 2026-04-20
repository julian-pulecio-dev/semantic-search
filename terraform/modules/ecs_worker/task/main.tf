resource "aws_cloudwatch_log_group" "ecs_page_slicing" {
  name              = "/ecs/${var.name}"
  retention_in_days = 14
}

resource "aws_iam_role" "ecs_task" {
  name = var.name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "ecs_s3_write" {
  name = "${var.name}-s3-write"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::${var.s3_bucket_name}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::${var.s3_bucket_name}"
      }
    ]
  })
}

resource "aws_iam_policy" "ecs_sqs_consume" {
  name = "${var.name}-sqs-consume"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.sqs_queue_arn
      }
    ]
  })
}

resource "aws_iam_policy" "ecs_bedrock_nova" {
  name = "${var.name}-bedrock-nova"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-*",
          "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_s3_write_attach" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_s3_write.arn
}

resource "aws_iam_role_policy_attachment" "ecs_sqs_consume_attach" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_sqs_consume.arn
}

resource "aws_iam_policy" "ecs_sqs_send_page_slicing" {
  name = "${var.name}-sqs-send-page-slicing"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = var.sqs_queue_arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_bedrock_nova_attach" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_bedrock_nova.arn
}

resource "aws_iam_role_policy_attachment" "ecs_sqs_send_page_slicing_attach" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_sqs_send_page_slicing.arn
}

resource "aws_ecs_task_definition" "page_slicing" {
  family                   = var.name
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"

  execution_role_arn = var.iam_role_arn
  task_role_arn      = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "page-slicing"
      image     = "julianpuleciodev/semantic-search"
      essential = true
      cpu       = 256
      memory    = 512
      command   = ["python", "-m", "workers.document_page_slicing.run"]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          # One log group, one stream per task: page-slicing/page-slicing/{task-id}
          # Streams persist in CloudWatch after the task is stopped or scaled in.
          awslogs-group         = aws_cloudwatch_log_group.ecs_page_slicing.name
          awslogs-region        = "us-east-1"
          awslogs-stream-prefix = "page-slicing"
        }
      }

      environment = var.environment_variables
      secrets     = var.secret_variables
    }
  ])
}
