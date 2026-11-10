import re
import unicodedata


def intent_label(value: str) -> str:
    suffix = re.compile(
        r"\s*(?:\((?:as\b|if\b|optional\b|required\b)[^()]*\)|\b(?:if different|optional|required)\b|\*+)\s*$",
        re.IGNORECASE,
    )
    previous = None
    while value != previous:
        previous = value
        value = suffix.sub("", value).strip()
    return value


def normalize(value: str) -> str:
    value = re.sub(
        r"linkedin|github", lambda match: match[0].lower(), value, flags=re.IGNORECASE
    )
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+|_", " ", value).split())


def normalize_question(value: str) -> str:
    value = re.sub(
        r"\b(?:max(?:imum)?|up to|limit(?:ed)? to)\s+\d+\s+words?\b",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return normalize(value)
