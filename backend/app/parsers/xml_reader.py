"""Streaming, safe XML reading for the XML formats (guide 12.3).

An export is an untrusted file: entity declarations can point at the server's own disk or
expand into gigabytes. defusedxml refuses entities and external references while still
allowing the DOCTYPE line that real PubMed exports carry. Elements are cleared as they are
consumed, so a 100,000-record file costs one record of memory, not the whole tree.
"""

import io
from collections.abc import Iterator
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import iterparse


class MalformedXMLError(Exception):
    """The file is not XML at all, or breaks off part way through."""


def records_of(text: str, tag: str) -> Iterator[tuple[int, Element]]:
    """Yield (ordinal, element) for every `tag` element, freeing each one afterwards.

    The ordinal counts records, not lines: XML parsers report positions the reader cannot
    map back to the file, and "record 42" is what the import report shows.
    """
    source = io.StringIO(text)
    ordinal = 0
    try:
        for event, element in iterparse(source, events=("end",), forbid_dtd=False):
            if event != "end" or element.tag != tag:
                continue
            ordinal += 1
            yield ordinal, element
            element.clear()
    except ParseError as error:
        raise MalformedXMLError(str(error)) from error


def children_of_root(text: str) -> Iterator[Element]:
    """Yield every direct child of the root element, freeing each one afterwards.

    For formats whose records are not one tag but whatever sits at the top level (RDF).
    """
    depth = 0
    try:
        for event, element in iterparse(
            io.StringIO(text), events=("start", "end"), forbid_dtd=False
        ):
            if event == "start":
                depth += 1
                continue
            depth -= 1
            if depth == 1:
                yield element
                element.clear()
    except ParseError as error:
        raise MalformedXMLError(str(error)) from error
