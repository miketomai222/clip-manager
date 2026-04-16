"""HTML utility functions shared across clip-manager packages."""

from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)


def strip_html(html: str) -> str:
    """Return the plain-text content of an HTML string, with tags removed."""
    extractor = _TextExtractor()
    extractor.feed(html)
    return "".join(extractor._parts)
