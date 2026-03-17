module "sqs_dead_letter_queue" {
  source = "./sqs_queue"
  name = "${var.name}-dead-letter-queue"
}

module "sqs_queue" {
  source = "./sqs_queue"
  name = "${var.name}-queue"
  create_dlq = true
  dlq_name = module.sqs_dead_letter_queue.name
}