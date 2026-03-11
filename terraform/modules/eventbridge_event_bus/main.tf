resource "aws_cloudwatch_event_bus" "document_bus" {
  name = var.event_bus_name
}

resource "aws_cloudwatch_event_permission" "allow_account" {
  principal    = "*"
  statement_id = "AllowAccountPutEvents"
  action       = "events:PutEvents"
}