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

    base = _search_xml(path, norm)
    if not base:
        return ""

    # "Art. 5(2)(b)" should land on the item, not on the whole article: the
    # article text is long enough that a truncated passage would never reach the
    # provision the reference is actually about.
    subs = _sub_references(article_ref)
    return _refine_eid(path, base, subs) or base if subs else base


def _sub_references(article_ref: str) -> list[str]:
    """['2', 'b'] from 'Art. 5(2)(b) InfoSoc'; empty when there is no sub-reference."""
    stripped = _LAW_SUFFIXES.sub("", article_ref.replace("\xa0", " "))
    return re.findall(r"\((\w+)\)", stripped)


def _refine_eid(path: Path, base_eid: str, subs: list[str]) -> str:
    """Walk from the article element into the paragraph/item the sub-reference names."""
    root = _load_tree(path)
    if root is None:
        return ""

    node = next((el for el in root.iter() if el.get("eId") == base_eid), None)
    if node is None:
        return ""

    for token in subs:
        child = _descendant_by_num(node, token)
        if child is None:
            break
        node = child

    return node.get("eId", "")


_NUMBERED_TAGS = {
    "paragraph", "subsection", "subparagraph", "item", "point", "level",
    "prov", "subprov", "indent", "alinea",
}


def _descendant_by_num(parent: etree._Element, token: str) -> etree._Element | None:
    """First numbered descendant of *parent* whose <num> matches *token*."""
    want = _num_token(token)
    for el in parent.iter():
        if el is parent or etree.QName(el.tag).localname not in _NUMBERED_TAGS:
            continue
        if not el.get("eId"):
            continue
        num_el = el.find(f"{{{AKN_NS}}}num")
        if num_el is not None and _num_token("".join(num_el.itertext())) == want:
            return el
    return None


def _num_token(text: str) -> str:
    """'(b)' → 'b', '2.' → '2', ' 1 ' → '1'."""
    return re.sub(r"[^0-9A-Za-z]", "", text or "").lower()


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

    # Walk every element; when <num> text matches, grab closest ancestor eId.
    # Article/section-level hits win over paragraph-level ones, so that a bare
    # number like "2" is not matched against paragraph 2 of Article 1.
    fallback = ""
    for el in root.iter():
        local = etree.QName(el.tag).localname
        if local == "num":
            num_text = _normalize_ref("".join(el.itertext()))
            if _refs_match(norm_ref, num_text):
                candidate = _closest_with_eid(el)
                if candidate is None:
                    continue
                eid = candidate.get("eId", "")
                if etree.QName(candidate.tag).localname in ("article", "section", "prov"):
                    return eid
                fallback = fallback or eid

    return fallback


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
    if _prefix_match(query, candidate):
        return True
    # French style: "L123-1" in candidate "L. 123-1" — normalise dots/spaces
    q2 = re.sub(r"[\s.]", "", query)
    c2 = re.sub(r"[\s.]", "", candidate)
    if q2 == c2 or _prefix_match(q2, c2):
        return True
    # The KG and the document may label the same provision differently:
    # "L123-1 CPI" vs "Article L123-1", "s. 12 CDPA" vs "12", "Art. 1" vs "Article 1".
    # Compare the bare numbers with the leading label removed on both sides.
    q3, c3 = _strip_label(query), _strip_label(candidate)
    if q3 and (q3 == c3 or _prefix_match(q3, c3)):
        return True
    return False


def _strip_label(ref: str) -> str:
    """Drop a leading provision label: 'Article L123-1' → 'L123-1', 's. 12' → '12'."""
    text = re.sub(
        r"^(articles?|artikel|art\.?|sections?|sec\.?|s\.|§)\s*",
        "",
        ref.strip(),
        flags=re.IGNORECASE,
    )
    return re.sub(r"[\s.]", "", text)


def _prefix_match(query: str, candidate: str) -> bool:
    """True if candidate starts with query and does not merely extend its number.

    Guards against "L123-1" matching "L123-10" or "§ 64" matching "§ 64a".
    """
    if not candidate.startswith(query):
        return False
    rest = candidate[len(query):]
    return not rest[:1].isalnum()
