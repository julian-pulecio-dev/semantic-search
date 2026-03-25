resource "aws_appautoscaling_target" "doc_chunking" {
  min_capacity       = 1
  max_capacity       = var.max_capacity
  resource_id        = "service/${var.cluster_name}/${var.service_name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# --- Scale-out policy: add 1 task per threshold breach ---

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${var.name}-scale-out"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.doc_chunking.resource_id
  scalable_dimension = aws_appautoscaling_target.doc_chunking.scalable_dimension
  service_namespace  = aws_appautoscaling_target.doc_chunking.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 60
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_lower_bound = 0
      scaling_adjustment          = 1
    }
  }
}

# Alarm based on Visible + NotVisible (in-flight) so messages being processed
# don't make the metric drop to 0 and prevent scale-out from firing.
resource "aws_cloudwatch_metric_alarm" "scale_out" {
  alarm_name          = "${var.name}-scale-out"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = var.scale_out_threshold
  alarm_actions       = [aws_appautoscaling_policy.scale_out.arn]

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

# --- Scale-in policy: remove 1 task when queue is fully empty for 3 consecutive minutes ---

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.name}-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.doc_chunking.resource_id
  scalable_dimension = aws_appautoscaling_target.doc_chunking.scalable_dimension
  service_namespace  = aws_appautoscaling_target.doc_chunking.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 300
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = -1
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "scale_in" {
  alarm_name          = "${var.name}-scale-in"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 3
  threshold           = 0
  alarm_actions       = [aws_appautoscaling_policy.scale_in.arn]

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
