resource "aws_appautoscaling_target" "ecs_worker" {
  min_capacity       = 0                                 # permite escalar a 0
  max_capacity       = var.max_capacity
  resource_id        = "service/${var.cluster_name}/${var.service_name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# --- Scale-out policy: multi-step para manejar bursts ---

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${var.name}-scale-out"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.ecs_worker.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_worker.service_namespace

  step_scaling_policy_configuration {
    adjustment_type          = "ExactCapacity"
    cooldown                 = 60
    metric_aggregation_type  = "Maximum"

    # any message in the queue: scale to 1 task
    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = var.scale_out_threshold
      scaling_adjustment          = 1
    }

    # 1× threshold: two tasks
    step_adjustment {
      metric_interval_lower_bound = var.scale_out_threshold
      metric_interval_upper_bound = var.scale_out_threshold * 5
      scaling_adjustment          = 2
    }

    # 5× threshold: three tasks
    step_adjustment {
      metric_interval_lower_bound = var.scale_out_threshold * 5
      scaling_adjustment          = 3
    }
  }
}

# Scale-out alarm: triggers with any message in the queue (threshold = 0)
resource "aws_cloudwatch_metric_alarm" "scale_out" {
  alarm_name          = "${var.name}-scale-out"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  alarm_actions       = [aws_appautoscaling_policy.scale_out.arn]
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "total"
    expression  = "visible + inflight"
    label       = "Total Messages (visible + in-flight)"
    return_data = true
  }

  metric_query {
    id = "visible"
    metric {
      metric_name = "ApproximateNumberOfMessagesVisible"
      namespace   = "AWS/SQS"
      period      = 60
      stat        = "Maximum"
      dimensions = {
        QueueName = var.sqs_queue_name
      }
    }
  }

  metric_query {
    id = "inflight"
    metric {
      metric_name = "ApproximateNumberOfMessagesNotVisible"
      namespace   = "AWS/SQS"
      period      = 60
      stat        = "Maximum"
      dimensions = {
        QueueName = var.sqs_queue_name
      }
    }
  }
}

# --- Scale-in policy: scale to 0 when the queue is empty ---

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.name}-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.ecs_worker.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_worker.service_namespace

  step_scaling_policy_configuration {
    adjustment_type          = "ExactCapacity"           # force to 0 directly
    cooldown                 = 300
    metric_aggregation_type  = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0                    # scale exactly to 0 tasks
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "scale_in" {
  alarm_name          = "${var.name}-scale-in"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 3
  threshold           = 0
  alarm_actions       = [aws_appautoscaling_policy.scale_in.arn]
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "total"
    expression  = "visible + inflight"
    label       = "Total Messages (visible + in-flight)"
    return_data = true
  }

  metric_query {
    id = "visible"
    metric {
      metric_name = "ApproximateNumberOfMessagesVisible"
      namespace   = "AWS/SQS"
      period      = 60
      stat        = "Maximum"
      dimensions = {
        QueueName = var.sqs_queue_name
      }
    }
  }

  metric_query {
    id = "inflight"
    metric {
      metric_name = "ApproximateNumberOfMessagesNotVisible"
      namespace   = "AWS/SQS"
      period      = 60
      stat        = "Maximum"
      dimensions = {
        QueueName = var.sqs_queue_name
      }
    }
  }
}