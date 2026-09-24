"""textstats 테스트."""

import unittest

from textstats import average_word_length, word_count


class WordCountTest(unittest.TestCase):
    def test_single_spaces(self):
        self.assertEqual(word_count("오늘 비가 온다"), 3)

    def test_repeated_and_edge_spaces(self):
        self.assertEqual(word_count("  오늘   비가 온다 "), 3)

    def test_empty(self):
        self.assertEqual(word_count(""), 0)


class AverageWordLengthTest(unittest.TestCase):
    def test_average(self):
        self.assertEqual(average_word_length("ab abcd"), 3.0)

    def test_empty(self):
        self.assertEqual(average_word_length("   "), 0.0)


if __name__ == "__main__":
    unittest.main()
