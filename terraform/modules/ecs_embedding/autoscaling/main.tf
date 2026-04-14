resource "aws_appautoscaling_target" "embedding" {
  min_capacity       = 0
  max_capacity       = var.max_capacity
  resource_id        = "service/${var.cluster_name}/${var.service_name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${var.name}-scale-out"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.embedding.resource_id
  scalable_dimension = aws_appautoscaling_target.embedding.scalable_dimension
  service_namespace  = aws_appautoscaling_target.embedding.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = var.scale_out_threshold
      scaling_adjustment          = 1
    }

    step_adjustment {
      metric_interval_lower_bound = var.scale_out_threshold
      metric_interval_upper_bound = var.scale_out_threshold * 5
      scaling_adjustment          = 2
    }

    step_adjustment {
      metric_interval_lower_bound = var.scale_out_threshold * 5
      scaling_adjustment          = 3
    }
  }
}

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

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.name}-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.embedding.resource_id
  scalable_dimension = aws_appautoscaling_target.embedding.scalable_dimension
  service_namespace  = aws_appautoscaling_target.embedding.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 300
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0
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
