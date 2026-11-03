import re


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how", "i",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "what", "when", "where",
    "which", "who", "why", "with",
}


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", text.lower()) if token not in STOPWORDS]


def normalize_phrase_text(text: str) -> str:
    """Lowercase text and collapse punctuation so phrases can be matched with spaces."""
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()).strip() + " "
