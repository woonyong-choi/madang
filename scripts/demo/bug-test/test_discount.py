"""할인 테스트."""

import unittest

from receipt import apply_discount


class ApplyDiscountTest(unittest.TestCase):
    """apply_discount 테스트."""

    def test_ten_percent(self):
        """10% 할인하면 10000원이 9000원이 된다."""
        self.assertEqual(apply_discount(10000, 10), 9000)


if __name__ == "__main__":
    unittest.main()
