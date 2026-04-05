resource "aws_appautoscaling_target" "doc_chunking" {
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
  resource_id        = aws_appautoscaling_target.doc_chunking.resource_id
  scalable_dimension = aws_appautoscaling_target.doc_chunking.scalable_dimension
  service_namespace  = aws_appautoscaling_target.doc_chunking.service_namespace

  step_scaling_policy_configuration {
    adjustment_type          = "ExactCapacity"           # desde 0, necesitamos capacidad exacta en el primer paso
    cooldown                 = 60
    metric_aggregation_type  = "Maximum"

    # Cualquier mensaje: arrancar al menos 1 tarea
    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = var.scale_out_threshold
      scaling_adjustment          = 1
    }

    # 1× threshold: 2 tareas
    step_adjustment {
      metric_interval_lower_bound = var.scale_out_threshold
      metric_interval_upper_bound = var.scale_out_threshold * 5
      scaling_adjustment          = 2
    }

    # 5× threshold: 3 tareas
    step_adjustment {
      metric_interval_lower_bound = var.scale_out_threshold * 5
      scaling_adjustment          = 3
    }
  }
}

# Alarma de scale-out: dispara con cualquier mensaje en la cola (threshold = 0)
resource "aws_cloudwatch_metric_alarm" "scale_out" {
  alarm_name          = "${var.name}-scale-out"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0                                # dispara con >= 1 mensaje
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

# --- Scale-in policy: escala a 0 cuando la cola está vacía ---

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.name}-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.doc_chunking.resource_id
  scalable_dimension = aws_appautoscaling_target.doc_chunking.scalable_dimension
  service_namespace  = aws_appautoscaling_target.doc_chunking.service_namespace

  step_scaling_policy_configuration {
    adjustment_type          = "ExactCapacity"           # forzar a 0 directamente
    cooldown                 = 300
    metric_aggregation_type  = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 0                    # escala exactamente a 0 tareas
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