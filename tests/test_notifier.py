import unittest
from unittest.mock import Mock, patch

from app.core.notifier import FeishuNotifier


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        self.text = str(payload)

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        return self.payload


class FeishuNotifierTests(unittest.TestCase):
    def setUp(self):
        self.notifier = FeishuNotifier({"url": "https://example.test/hook"})

    @patch("app.core.notifier.time.sleep")
    @patch("app.core.notifier.requests.post")
    def test_internal_error_is_retried_then_succeeds(self, post, sleep):
        post.side_effect = [
            FakeResponse(200, {"code": 19006, "msg": "internal error"}),
            FakeResponse(200, {"code": 0}),
        ]

        self.assertTrue(self.notifier.send_card("日报"))
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("app.core.notifier.time.sleep")
    @patch("app.core.notifier.requests.post")
    def test_final_failure_sends_one_alert_to_fallback_webhook(self, post, sleep):
        fallback = Mock()
        fallback.send_card.return_value = True
        notifier = FeishuNotifier({"url": "https://example.test/hook"}, fallback)
        post.return_value = FakeResponse(200, {"code": 19006, "msg": "internal error"})

        self.assertFalse(notifier.send_card("日报"))
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_args_list[0].args, (1,))
        self.assertEqual(sleep.call_args_list[1].args, (2,))
        fallback.send_card.assert_called_once()
        self.assertFalse(fallback.send_card.call_args.kwargs["notify_on_failure"])

    @patch("app.core.notifier.requests.post")
    def test_non_retryable_error_still_notifies_fallback(self, post):
        fallback = Mock()
        fallback.send_card.return_value = True
        notifier = FeishuNotifier({"url": "https://example.test/hook"}, fallback)
        post.return_value = FakeResponse(400, {"code": 9499, "msg": "bad request"})

        self.assertFalse(notifier.send_card("日报"))
        self.assertEqual(post.call_count, 1)
        fallback.send_card.assert_called_once()


if __name__ == "__main__":
    unittest.main()
