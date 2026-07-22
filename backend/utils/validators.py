import re

ENGLISH_WIKIPEDIA_REGEX = re.compile(
    r"^https://en\.wikipedia\.org/wiki/.+$"
)


def is_valid_english_wikipedia_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    return bool(ENGLISH_WIKIPEDIA_REGEX.match(url.strip()))
