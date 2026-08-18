import unittest
from datetime import UTC, datetime

from app.time_utils import format_israel_datetime, israel_now


class TimeUtilsTests(unittest.TestCase):
    def test_israel_now_returns_iso_timestamp_in_jerusalem_timezone(self):
        timestamp = israel_now()
        parsed = datetime.fromisoformat(timestamp)

        self.assertIsNotNone(parsed.tzinfo)
        self.assertIn(parsed.utcoffset().total_seconds(), (7200, 10800))

    def test_format_israel_datetime_converts_from_utc(self):
        timestamp = datetime(2026, 8, 18, 11, 35, tzinfo=UTC)

        self.assertEqual("18/08/2026 14:35", format_israel_datetime(timestamp))


if __name__ == "__main__":
    unittest.main()
