"""Map article references (e.g. '§ 64 UrhG', 'Art. 29 URG') to AKN eIds.

Strategy:
1. Normalize the reference (strip law name suffix, whitespace, non-breaking spaces)
2. Walk the XML looking for <num> text that matches
3. Return the eId of the smallest containing article/section element
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

_ARTICLE_TAGS = {"article", "section", "paragraph", "prov"}

# Suffixes to strip from article refs like "§ 64 UrhG" → "§ 64"
_LAW_SUFFIXES = re.compile(
    r"\s+(UrhG|URG|CopA|LDA|CDPA|CPI|LDA|C-42|17 U\.S\.C\.|"
    r"Copyright Act|InfoSoc|Directive \S+|Rental Directive|Software Directive).*$",
    re.IGNORECASE,
)

# Known article ref → eId overrides for docs that don't use standard numbering
_OVERRIDES: dict[tuple[str, str], str] = {
    # (local_path_stem, normalized_ref)
}


def find_eid(local_path: str, article_ref: str) -> str:
    """Return the best matching eId for *article_ref* in the AKN document at *local_path*.

    Returns "" if nothing matches.
    """
    if not local_path or not article_ref:
        return ""

    path = Path(local_path)
    if not path.exists():
        return ""

    norm = _normalize_ref(article_ref)
    if not norm:
        return ""

    return _search_xml(path, norm)


@lru_cache(maxsize=16)
def _load_tree(path: Path) -> etree._Element | None:
    try:
        return etree.parse(str(path)).getroot()
    except Exception:
        return None


def _search_xml(path: Path, norm_ref: str) -> str:
    root = _load_tree(path)
    if root is None:
        return ""

    # Walk every element; when <num> text matches, grab closest ancestor eId
    for el in root.iter():
        local = etree.QName(el.tag).localname
        if local == "num":
            num_text = _normalize_ref("".join(el.itertext()))
            if _refs_match(norm_ref, num_text):
                candidate = _closest_with_eid(el)
                if candidate is not None:
                    return candidate.get("eId", "")

    return ""


def _closest_with_eid(el: etree._Element) -> etree._Element | None:
    """Walk up the tree to find the nearest element that has an eId."""
    node = el
    while node is not None:
        if node.get("eId"):
            return node
        node = node.getparent()
    return None


def _normalize_ref(ref: str) -> str:
    """Strip law suffixes, normalise whitespace and non-breaking spaces."""
    text = ref.replace("\xa0", " ")       # non-breaking space → regular space
    text = _LAW_SUFFIXES.sub("", text)    # remove "UrhG", "URG", etc.
    text = re.sub(r"\s+", " ", text).strip()
    # Strip trailing paragraph ref "(2)(a)" etc. — keep only top-level number
    text = re.sub(r"\(\d+\).*$", "", text).strip()
    return text


def _refs_match(query: str, candidate: str) -> bool:
    """Return True if query ref is a prefix-match of candidate or equal."""
    if not query or not candidate:
        return False
    # Exact match
    if query == candidate:
        return True
    # Candidate starts with query (handles "§ 64" matching "§ 64 Allgemeines")
    if candidate.startswith(query):
        return True
    # French style: "L123-1" in candidate "L. 123-1" — normalise dots/spaces
    q2 = re.sub(r"[\s.]", "", query)
    c2 = re.sub(r"[\s.]", "", candidate)
    return q2 == c2 or c2.startswith(q2)
