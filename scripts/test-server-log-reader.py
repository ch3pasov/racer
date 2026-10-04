#!/usr/bin/env python3
"""Offline regression coverage for Open Cloud log-reader transport failures."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error


READER_PATH = Path(__file__).with_name("read-roblox-server-logs.py")
SPEC = importlib.util.spec_from_file_location("racer_server_log_reader", READER_PATH)
assert SPEC is not None and SPEC.loader is not None
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


class ReadTimeout(io.BytesIO):
    def read(self, *args, **kwargs):
        raise TimeoutError("timed out while reading response")


class LogReaderTransportTests(unittest.TestCase):
    def setUp(self):
        # All network calls and waits are replaced; no environment key is read.
        self.open = self.enterContext(patch.object(reader.urllib.request, "urlopen"))
        self.sleep = self.enterContext(patch.object(reader.time, "sleep"))

    def request(self):
        return reader.request_json("/test", {}, "offline-test-key")

    def test_connection_timeout_recovers_on_next_attempt(self):
        self.open.side_effect = [TimeoutError("timed out"), io.BytesIO(b'{"ok": true}')]

        self.assertEqual(self.request(), {"ok": True})
        self.assertEqual(self.open.call_count, 2)
        self.sleep.assert_called_once_with(1)

    def test_response_read_timeout_recovers_and_closes_response(self):
        timed_out = ReadTimeout()
        self.open.side_effect = [timed_out, io.BytesIO(b'{"ok": true}')]

        self.assertEqual(self.request(), {"ok": True})
        self.assertTrue(timed_out.closed)
        self.assertEqual(self.open.call_count, 2)
        self.sleep.assert_called_once_with(1)

    def test_repeated_timeouts_fail_with_controlled_error_after_bounded_retries(self):
        self.open.side_effect = TimeoutError("timed out")

        with self.assertRaisesRegex(reader.RobloxLogsError, "Could not reach Roblox Open Cloud"):
            self.request()

        self.assertEqual(self.open.call_count, reader.DEFAULT_MAX_RETRIES + 1)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1, 2, 4, 8])

    def test_url_error_keeps_existing_retry_behavior(self):
        self.open.side_effect = [urllib.error.URLError("unavailable"), io.BytesIO(b'{}')]

        self.assertEqual(self.request(), {})
        self.sleep.assert_called_once_with(1)

    def test_rate_limit_is_retried(self):
        self.open.side_effect = [
            urllib.error.HTTPError("https://example.invalid", 429, "limited", {}, io.BytesIO()),
            io.BytesIO(b'{}'),
        ]

        self.assertEqual(self.request(), {})
        self.sleep.assert_called_once_with(1)

    def test_authorization_error_is_not_retried(self):
        self.open.side_effect = urllib.error.HTTPError(
            "https://example.invalid", 403, "forbidden", {}, io.BytesIO(b"denied")
        )

        with self.assertRaisesRegex(reader.RobloxLogsError, "HTTP 403: denied"):
            self.request()

        self.assertEqual(self.open.call_count, 1)
        self.sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
