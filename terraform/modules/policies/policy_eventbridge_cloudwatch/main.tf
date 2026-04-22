data "aws_iam_policy_document" "eventbridge_logs" {
  statement {
    sid    = "AllowEventBridgeDelivery"
    effect = "Allow"

    principals {
      type = "Service"
      identifiers = [
        "events.amazonaws.com",
        "delivery.logs.amazonaws.com"
      ]
    }

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = ["arn:aws:logs:*:*:log-group:*"]
  }
}

resource "aws_cloudwatch_log_resource_policy" "eventbridge_logs" {
  policy_name     = var.name
  policy_document = data.aws_iam_policy_document.eventbridge_logs.json
}