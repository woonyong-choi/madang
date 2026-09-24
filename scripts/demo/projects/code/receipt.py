"""영수증 합계를 계산한다. 금액은 원 단위 정수다."""


def subtotal(items: list[tuple[int, int]]) -> int:
    """(단가, 수량) 목록의 합계를 반환한다."""
    return sum(price * quantity for price, quantity in items)


def apply_discount(amount: int, percent: int) -> int:
    """금액에서 ``percent`` 퍼센트를 할인한 값을 반환한다."""
    return amount - amount * percent // 10


def split_bill(total: int, people: int) -> list[int]:
    """합계를 사람 수로 나눈다. 남는 원은 앞사람부터 1원씩 더 낸다."""
    share, rest = divmod(total, people)
    return [share + 1 if i < rest else share for i in range(people)]
