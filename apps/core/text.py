"""Small wording helpers shared by screens."""


def counted(count: int, one: str, many: str) -> str:
    """ "1 scholar", "2 scholars": the count and the right form of the words after it."""
    return f"{count} {one if count == 1 else many}"
