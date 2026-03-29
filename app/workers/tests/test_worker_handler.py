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


class TestWorkerHandlerStop(SimpleTestCase):
    def _make_worker(self, **kwargs):
        defaults = dict(
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
            max_workers=2,
            visibility_timeout=60,
            processor=ConcreteHandler(),
        )
        defaults.update(kwargs)
        return WorkerHandler(**defaults)

    def test_stop_sets_stop_event(self):
        worker = self._make_worker()
        self.assertFalse(worker._stop_event.is_set())
        worker.stop()
        self.assertTrue(worker._stop_event.is_set())

    def test_stop_accepts_signal_args(self):
        worker = self._make_worker()
        worker.stop(2, None)  # SIGINT signature
        self.assertTrue(worker._stop_event.is_set())


class TestWorkerHandlerSqsClient(SimpleTestCase):
    def _make_worker(self):
        return WorkerHandler(
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
            max_workers=2,
            visibility_timeout=60,
            processor=ConcreteHandler(),
        )

    @patch("workers.worker_handler.boto3.session.Session")
    def test_get_sqs_client_creates_client_lazily(self, mock_session_cls):
        worker = self._make_worker()
        mock_client = MagicMock()
        mock_session_cls.return_value.client.return_value = mock_client

        client = worker._get_sqs_client()

        self.assertIs(client, mock_client)
        mock_session_cls.return_value.client.assert_called_once_with(
            "sqs", region_name="us-east-1"
        )

    @patch("workers.worker_handler.boto3.session.Session")
    def test_get_sqs_client_reuses_same_client(self, mock_session_cls):
        worker = self._make_worker()
        mock_client = MagicMock()
        mock_session_cls.return_value.client.return_value = mock_client

        first = worker._get_sqs_client()
        second = worker._get_sqs_client()

        self.assertIs(first, second)
        mock_session_cls.return_value.client.assert_called_once()


class TestHeartbeatLoop(SimpleTestCase):
    def _make_worker(self, visibility_timeout=60):
        return WorkerHandler(
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
            max_workers=2,
            visibility_timeout=visibility_timeout,
            processor=ConcreteHandler(),
        )

    def test_heartbeat_stops_immediately_when_done_event_set(self):
        worker = self._make_worker()
        sqs = MagicMock()
        done_event = threading.Event()
        done_event.set()

        worker._heartbeat_loop(sqs, "receipt-handle", done_event)

        sqs.change_message_visibility.assert_not_called()

    def test_heartbeat_extends_visibility_timeout(self):
        worker = self._make_worker(visibility_timeout=60)
        sqs = MagicMock()
        done_event = threading.Event()

        call_count = {"n": 0}

        def fake_wait(timeout):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                done_event.set()
                return True
            return False

        done_event.wait = fake_wait

        worker._heartbeat_loop(sqs, "receipt-handle-123", done_event)

        sqs.change_message_visibility.assert_called_with(
            QueueUrl=worker.queue_url,
            ReceiptHandle="receipt-handle-123",
            VisibilityTimeout=60,
        )

    def test_heartbeat_stops_when_stop_event_set(self):
        worker = self._make_worker()
        sqs = MagicMock()
        done_event = threading.Event()

        worker._stop_event.set()

        def fake_wait(timeout):
            return False

        done_event.wait = fake_wait

        worker._heartbeat_loop(sqs, "receipt-handle", done_event)

        sqs.change_message_visibility.assert_not_called()

    def test_heartbeat_swallows_visibility_extension_errors(self):
        worker = self._make_worker(visibility_timeout=60)
        sqs = MagicMock()
        sqs.change_message_visibility.side_effect = Exception("network error")
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
        worker._heartbeat_loop(sqs, "receipt-handle", done_event)


class TestProcessMessage(SimpleTestCase):
    def _make_worker(self, processor):
        return WorkerHandler(
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
            max_workers=2,
            visibility_timeout=60,
            processor=processor,
        )

    def _make_message(self, message_id="msg-1", receipt_handle="rh-1"):
        return {
            "MessageId": message_id,
            "ReceiptHandle": receipt_handle,
            "Body": "{}",
        }

    @patch("workers.worker_handler.boto3.session.Session")
    def test_process_message_success_deletes_message_and_calls_hooks(
        self, mock_session_cls
    ):
        processor = MagicMock(spec=Handler)
        worker = self._make_worker(processor)

        mock_sqs = MagicMock()
        mock_session_cls.return_value.client.return_value = mock_sqs

        message = self._make_message()
        worker._process_message(message)

        processor.handle.assert_called_once_with(message)
        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl=worker.queue_url, ReceiptHandle="rh-1"
        )
        processor.on_success.assert_called_once_with(message)
        processor.cleanup.assert_called_once()

    @patch("workers.worker_handler.boto3.session.Session")
    def test_process_message_failure_calls_on_error_and_cleanup(
        self, mock_session_cls
    ):
        processor = MagicMock(spec=Handler)
        error = ValueError("something broke")
        processor.handle.side_effect = error
        worker = self._make_worker(processor)

        mock_sqs = MagicMock()
        mock_session_cls.return_value.client.return_value = mock_sqs

        message = self._make_message()
        worker._process_message(message)

        mock_sqs.delete_message.assert_not_called()
        processor.on_error.assert_called_once_with(message, error)
        processor.cleanup.assert_called_once()

    @patch("workers.worker_handler.boto3.session.Session")
    def test_process_message_cleanup_always_called(self, mock_session_cls):
        processor = MagicMock(spec=Handler)
        processor.handle.side_effect = RuntimeError("crash")
        worker = self._make_worker(processor)

        mock_sqs = MagicMock()
        mock_session_cls.return_value.client.return_value = mock_sqs

        worker._process_message(self._make_message())

        processor.cleanup.assert_called_once()


class TestAcquireAvailableSlots(SimpleTestCase):
    def _make_worker(self, max_workers=4):
        return WorkerHandler(
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
            max_workers=max_workers,
            visibility_timeout=60,
            processor=ConcreteHandler(),
        )

    def test_acquires_up_to_max_workers_when_all_free(self):
        worker = self._make_worker(max_workers=4)
        slots = worker._acquire_available_slots()
        self.assertGreaterEqual(slots, 1)
        self.assertLessEqual(slots, 4)

    def test_acquires_zero_when_all_slots_taken(self):
        worker = self._make_worker(max_workers=2)
        # Drain the semaphore completely
        worker._semaphore.acquire()
        worker._semaphore.acquire()

        slots = worker._acquire_available_slots()
        self.assertEqual(slots, 0)

    def test_releases_slots_equal_to_acquired(self):
        worker = self._make_worker(max_workers=4)
        before = worker._semaphore._value
        slots = worker._acquire_available_slots()
        after = worker._semaphore._value
        self.assertEqual(before - slots, after)
