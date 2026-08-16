import unittest

from app.keywords import find_matching_keywords


class KeywordTests(unittest.TestCase):
    def test_matches_original_and_translated_text_without_duplicates(self):
        matches = find_matching_keywords(
            "إطلاقُ نار قرب القرية",
            "דיווח על חדירה באזור נריה",
            ["إطلاق نار", "חדירה", "נריה", "חדירה"],
        )

        self.assertEqual(["إطلاق نار", "חדירה", "נריה"], matches)

    def test_does_not_match_unrelated_text(self):
        self.assertEqual([], find_matching_keywords("خبر عادي", "דיווח רגיל", ["פיגוע"]))


if __name__ == "__main__":
    unittest.main()
