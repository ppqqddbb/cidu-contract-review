import re
import unicodedata


def normalize_text(text: str, form: str = "NFC") -> str:
    text = unicodedata.normalize(form, text or "")
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", normalize_text(text))

