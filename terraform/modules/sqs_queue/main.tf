resource "aws_sqs_queue" "terraform_queue" {
  name                      = var.name
  delay_seconds             = var.delay_seconds
  max_message_size          = var.max_message_size
  message_retention_seconds = var.message_retention_seconds
  receive_wait_time_seconds = var.receive_wait_time_seconds

  redrive_policy = var.create_dlq ? jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter_queue[0].arn
    maxReceiveCount     = var.max_receive_count
  }) : null
}

resource "aws_sqs_queue" "dead_letter_queue" {
  count = var.create_dlq ? 1 : 0

  name = var.dlq_name
}

resource "aws_sqs_queue_redrive_allow_policy" "redrive_allow_policy" {
  count = var.create_dlq ? 1 : 0

  queue_url = aws_sqs_queue.dead_letter_queue[0].id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.terraform_queue.arn]
  })
}

resource "aws_sqs_queue_policy" "allow_eventbridge" {
  queue_url = aws_sqs_queue.terraform_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "AllowEventBridgeSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.terraform_queue.arn
      }
    ]
  })
}

