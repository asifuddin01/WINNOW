"""Normalisation shared by blocking and similarity scoring."""

import unicodedata
from html.parser import HTMLParser


class _TitleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _without_html(title: str) -> str:
    parser = _TitleTextExtractor()
    parser.feed(title)
    parser.close()
    return " ".join(parser.parts)


def normalise_title(title: str) -> str:
    """Return the database-compatible normal form for one title.

    The input is arbitrary Unicode title text. The output is lowercase text with HTML
    tags, accents and punctuation removed, and whitespace collapsed. Punctuation becomes
    a space so adjacent words do not get joined. Runtime and additional memory are O(n)
    for a title of length n. This also implements the HTML-removal detail in guide 8.3.
    """

    without_tags = _without_html(title).lower()
    decomposed = unicodedata.normalize("NFKD", without_tags)
    characters = (
        " " if unicodedata.category(character).startswith("P") else character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join("".join(characters).split())
