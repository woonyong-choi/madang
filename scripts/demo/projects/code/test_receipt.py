"""합계와 나누기 테스트."""

import unittest

from receipt import split_bill, subtotal


class SubtotalTest(unittest.TestCase):
    """subtotal 테스트."""

    def test_items(self):
        """단가와 수량을 곱해 더한다."""
        self.assertEqual(subtotal([(3000, 2), (1500, 1)]), 7500)

    def test_empty(self):
        """항목이 없으면 0원이다."""
        self.assertEqual(subtotal([]), 0)


class SplitBillTest(unittest.TestCase):
    """split_bill 테스트."""

    def test_even(self):
        """나누어떨어지면 모두 같은 금액이다."""
        self.assertEqual(split_bill(9000, 3), [3000, 3000, 3000])

    def test_rest_goes_first(self):
        """남는 원은 앞사람부터 1원씩 더 낸다."""
        self.assertEqual(split_bill(10001, 3), [3334, 3334, 3333])


if __name__ == "__main__":
    unittest.main()
