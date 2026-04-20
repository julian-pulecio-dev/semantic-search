import logging
import threading
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase
from workers.worker_handler import WorkerHandler
from workers.handler import Handler

logging.disable(logging.CRITICAL)


class ConcreteHandler(Handler):
    def handle(self, message):
        pass


def _make_worker(**kwargs):
    defaults = dict(
        queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
        visibility_timeout=60,
        processor=ConcreteHandler,
    )
    defaults.update(kwargs)
    with patch("workers.worker_handler.boto3.client"):
        return WorkerHandler(**defaults)


class TestWorkerHandlerStop(SimpleTestCase):
    def test_stop_sets_stop_event(self):
        worker = _make_worker()
        self.assertFalse(worker._stop_event.is_set())
        worker.stop()
        self.assertTrue(worker._stop_event.is_set())

    def test_stop_accepts_signal_args(self):
        worker = _make_worker()
        worker.stop(2, None)  # SIGINT signature
        self.assertTrue(worker._stop_event.is_set())


class TestHeartbeatLoop(SimpleTestCase):
    def test_heartbeat_stops_immediately_when_done_event_set(self):
        worker = _make_worker()
        worker._sqs = MagicMock()
        done_event = threading.Event()
        done_event.set()

        worker._heartbeat_loop("receipt-handle", done_event)

        worker._sqs.change_message_visibility.assert_not_called()

    def test_heartbeat_extends_visibility_timeout(self):
        worker = _make_worker(visibility_timeout=60)
        worker._sqs = MagicMock()
        done_event = threading.Event()

        call_count = {"n": 0}

        def fake_wait(timeout):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                done_event.set()
                return True
            return False

        done_event.wait = fake_wait

        worker._heartbeat_loop("receipt-handle-123", done_event)

        worker._sqs.change_message_visibility.assert_called_with(
            QueueUrl=worker.queue_url,
            ReceiptHandle="receipt-handle-123",
            VisibilityTimeout=60,
        )

    def test_heartbeat_stops_when_stop_event_set(self):
        worker = _make_worker()
        worker._sqs = MagicMock()
        done_event = threading.Event()
        worker._stop_event.set()

        def fake_wait(timeout):
            return False

        done_event.wait = fake_wait

        worker._heartbeat_loop("receipt-handle", done_event)

        worker._sqs.change_message_visibility.assert_not_called()

    def test_heartbeat_swallows_visibility_extension_errors(self):
        worker = _make_worker(visibility_timeout=60)
        worker._sqs = MagicMock()
        worker._sqs.change_message_visibility.side_effect = Exception(
            "network error"
        )
        done_event = threading.Event()

        call_count = {"n": 0}

        def fake_wait(timeout):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                done_event.set()
                return True
            return False

        done_event.wait = fake_wait

        # should not raise
        worker._heartbeat_loop("receipt-handle", done_event)


class TestProcessMessage(SimpleTestCase):
    def _make_message(self, message_id="msg-1", receipt_handle="rh-1"):
        return {
            "MessageId": message_id,
            "ReceiptHandle": receipt_handle,
            "Body": "{}",
        }

    def test_process_message_success_deletes_message_and_calls_hooks(self):
        mock_instance = MagicMock()
        mock_processor_cls = MagicMock(return_value=mock_instance)

        worker = _make_worker(processor=mock_processor_cls)
        worker._sqs = MagicMock()

        message = self._make_message()
        worker._process_message(message)

        mock_instance.handle.assert_called_once_with(message)
        worker._sqs.delete_message.assert_called_once_with(
            QueueUrl=worker.queue_url, ReceiptHandle="rh-1"
        )
        mock_instance.on_success.assert_called_once_with(message)
        mock_instance.cleanup.assert_called_once()

    def test_process_message_failure_calls_on_error_and_cleanup(self):
        mock_instance = MagicMock()
        error = ValueError("something broke")
        mock_instance.handle.side_effect = error
        mock_processor_cls = MagicMock(return_value=mock_instance)

        worker = _make_worker(processor=mock_processor_cls)
        worker._sqs = MagicMock()

        message = self._make_message()
        worker._process_message(message)

        worker._sqs.delete_message.assert_not_called()
        mock_instance.on_error.assert_called_once_with(message, error)
        mock_instance.cleanup.assert_called_once()

    def test_process_message_cleanup_always_called(self):
        mock_instance = MagicMock()
        mock_instance.handle.side_effect = RuntimeError("crash")
        mock_processor_cls = MagicMock(return_value=mock_instance)

        worker = _make_worker(processor=mock_processor_cls)
        worker._sqs = MagicMock()

        worker._process_message(self._make_message())

        mock_instance.cleanup.assert_called_once()
