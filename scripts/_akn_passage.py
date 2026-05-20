"""Extract a plain-text passage from an AKN element by eId."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_SKIP_TAGS = {"authorialNote", "meta", "identification", "references", "publication"}


@lru_cache(maxsize=16)
def _load(path: str) -> etree._Element | None:
    try:
        return etree.parse(path).getroot()
    except Exception:
        return None


def extract_passage(local_path: str, eid: str, max_chars: int = 800) -> str:
    """Return plain text of the AKN element with *eid* (truncated to *max_chars*)."""
    if not local_path or not eid:
        return ""
    p = Path(local_path)
    if not p.exists():
        return ""

    root = _load(str(p))
    if root is None:
        return ""

    for el in root.iter():
        if el.get("eId") == eid:
            text = _collect(el).strip()
            return text[:max_chars] if len(text) > max_chars else text

    return ""


def _collect(el: etree._Element) -> str:
    chunks: list[str] = []
    _walk(el, chunks)
    return "".join(chunks)


def _walk(el: etree._Element, out: list[str]) -> None:
    if etree.QName(el.tag).localname in _SKIP_TAGS:
        return
    if el.text:
        out.append(el.text)
    for child in el:
        _walk(child, out)
        if child.tail:
            out.append(child.tail)
