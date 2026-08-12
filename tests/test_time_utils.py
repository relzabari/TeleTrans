import unittest
from datetime import datetime

from app.time_utils import israel_now


class TimeUtilsTests(unittest.TestCase):
    def test_israel_now_returns_iso_timestamp_in_jerusalem_timezone(self):
        timestamp = israel_now()
        parsed = datetime.fromisoformat(timestamp)

        self.assertIsNotNone(parsed.tzinfo)
        self.assertIn(parsed.utcoffset().total_seconds(), (7200, 10800))


if __name__ == "__main__":
    unittest.main()
