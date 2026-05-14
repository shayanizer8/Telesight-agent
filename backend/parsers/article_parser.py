import re
from html.parser import HTMLParser

import httpx


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def parse_article(url: str) -> str:
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()

        parser = _TextExtractor()
        parser.feed(response.text)
        parser.close()

        text = " ".join(parser.parts)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as exc:
        raise RuntimeError(f"Failed to parse article from '{url}': {exc}") from exc