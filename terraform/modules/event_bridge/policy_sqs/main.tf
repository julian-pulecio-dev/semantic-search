data "aws_iam_policy_document" "eventbridge_sqs" {
  statement {
    sid    = "AllowEventBridgeSendMessage"
    effect = "Allow"

    principals {
      type = "Service"
      identifiers = [
        "events.amazonaws.com"
      ]
    }

    actions = [
      "sqs:SendMessage"
    ]

    resources = [
      var.sqs_url
    ]
  }
}

resource "aws_sqs_queue_policy" "eventbridge_sqs" {
  queue_url = var.sqs_url
  policy    = data.aws_iam_policy_document.eventbridge_sqs.json
}