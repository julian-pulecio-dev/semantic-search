data "aws_iam_policy_document" "eventbridge_sqs" {
    statement {
        sid    = "AllowSpecificEventBridgeRule"
        effect = "Allow"

        principals {
            type        = "Service"
            identifiers = ["events.amazonaws.com"]
        }

        actions = [
            "sqs:SendMessage"
        ]

        resources = [
            var.sqs_arn
        ]

        condition {
            test     = "ArnEquals"
            variable = "aws:SourceArn"
            values   = [var.event_rule_arn]
        }
    }
}

resource "aws_sqs_queue_policy" "eventbridge_sqs" {
  queue_url = var.sqs_url
  policy    = data.aws_iam_policy_document.eventbridge_sqs.json
}