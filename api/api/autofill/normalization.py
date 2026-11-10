import re
import unicodedata


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
