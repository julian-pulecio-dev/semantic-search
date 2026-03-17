resource "aws_cloudwatch_event_target" "sqs_target" {
  rule           = var.rule_name
  event_bus_name = "default"
  arn            = var.target_arn
  depends_on = [
    var.bucket_dependency
  ]

}

data "aws_iam_policy_document" "eventbridge_sqs" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    actions = [
      "sqs:SendMessage"
    ]

    resources = [
      var.target_arn
    ]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"

      values = [
        var.event_rule_arn
      ]
    }
  }
}

resource "aws_sqs_queue_policy" "allow_eventbridge" {
  queue_url = var.target_id
  policy    = data.aws_iam_policy_document.eventbridge_sqs.json
}