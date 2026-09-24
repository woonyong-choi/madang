"""글의 단어 수와 평균 단어 길이를 센다."""


def word_count(text: str) -> int:
    """공백으로 나뉜 단어 수를 반환한다."""
    return len(text.split(" "))


def average_word_length(text: str) -> float:
    """단어 길이의 평균을 반환한다. 단어가 없으면 0.0이다."""
    words = text.split()
    if not words:
        return 0.0
    return sum(len(word) for word in words) / len(words)
