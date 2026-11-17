"""Small wording helpers shared by screens."""


def counted(count: int, one: str, many: str) -> str:
    """ "1 scholar", "2 scholars": the count and the right form of the words after it."""
    return f"{count} {one if count == 1 else many}"


def normalize_newlines(value: str) -> str:
    """Browsers send line breaks as CRLF but count them as one character: store LF, so a text
    that fit the box also fits the limit."""
    return value.replace("\r\n", "\n").replace("\r", "\n")
