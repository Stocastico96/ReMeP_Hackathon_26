#!/usr/bin/env python3
"""shared utilities for the wipo akn pipeline."""

from __future__ import annotations

import datetime as _dt
import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

ARTICLE_SUFFIXES = (
    "bis",
    "ter",
    "quater",
    "quinquies",
    "sexies",
    "septies",
    "octies",
    "nonies",
    "decies",
)


@dataclass(frozen=True)
class TreatySpec:
    input_file: str
    short_name: str
    subtype: str
    year: int


# treaty mapping (verified against wipo treaty pages and local treaty pdfs).
TREATY_SPECS: Dict[str, TreatySpec] = {
    "1883_Paris_clean.html": TreatySpec("1883_Paris_clean.html", "paris", "convention", 1883),
    "1886_Berne_clean.html": TreatySpec("1886_Berne_clean.html", "berne", "convention", 1886),
    "1891_Madrid_Marks_clean.html": TreatySpec("1891_Madrid_Marks_clean.html", "madrid-marks", "agreement", 1891),
    "1891_Madrid_Source_clean.html": TreatySpec("1891_Madrid_Source_clean.html", "madrid-source", "agreement", 1891),
    "1928_Hague_clean.html": TreatySpec("1928_Hague_clean.html", "hague", "agreement", 1928),
    "1957_Nice_clean.html": TreatySpec("1957_Nice_clean.html", "nice", "agreement", 1957),
    "1958_Lisbon_clean.html": TreatySpec("1958_Lisbon_clean.html", "lisbon", "agreement", 1958),
    "1961_Rome_clean.html": TreatySpec("1961_Rome_clean.html", "rome", "convention", 1961),
    "1967_WIPO_clean.html": TreatySpec("1967_WIPO_clean.html", "wipo-convention", "convention", 1967),
    "1968_Locarno_clean.html": TreatySpec("1968_Locarno_clean.html", "locarno", "agreement", 1968),
    "1970_Washington_clean.html": TreatySpec("1970_Washington_clean.html", "pct", "treaty", 1970),
    "1971_Geneva_clean.html": TreatySpec("1971_Geneva_clean.html", "phonograms", "convention", 1971),
    "1971_Strasbourg_clean.html": TreatySpec("1971_Strasbourg_clean.html", "strasbourg", "agreement", 1971),
    "1973_Vienna_clean.html": TreatySpec("1973_Vienna_clean.html", "vienna", "agreement", 1973),
    "1974_Brussels_clean.html": TreatySpec("1974_Brussels_clean.html", "brussels", "convention", 1974),
    "1977_Budapest_clean.html": TreatySpec("1977_Budapest_clean.html", "budapest", "treaty", 1977),
    "1981_Nairobi_clean.html": TreatySpec("1981_Nairobi_clean.html", "nairobi", "treaty", 1981),
    "1989_Madrid_clean.html": TreatySpec("1989_Madrid_clean.html", "madrid-protocol", "protocol", 1989),
    "1989_Washington_clean.html": TreatySpec("1989_Washington_clean.html", "washington", "treaty", 1989),
    "1994_Geneva_clean.html": TreatySpec("1994_Geneva_clean.html", "tlt", "treaty", 1994),
    "1996_Berne_clean.html": TreatySpec("1996_Berne_clean.html", "wct", "treaty", 1996),
    "1996_Geneva_clean.html": TreatySpec("1996_Geneva_clean.html", "wppt", "treaty", 1996),
    "2000_Geneva_clean.html": TreatySpec("2000_Geneva_clean.html", "plt", "treaty", 2000),
    "2006_Singepore_clean.html": TreatySpec("2006_Singepore_clean.html", "singapore", "treaty", 2006),
    "2012_Beijing_clean.html": TreatySpec("2012_Beijing_clean.html", "beijing", "treaty", 2012),
    "2013_Marrakesh_clean.html": TreatySpec("2013_Marrakesh_clean.html", "marrakesh", "treaty", 2013),
    "2024_Geneva_clean.html": TreatySpec("2024_Geneva_clean.html", "gratk", "treaty", 2024),
    "2024_Riyadh_clean.html": TreatySpec("2024_Riyadh_clean.html", "rdlt", "treaty", 2024),
}

# alias map used by enrichment script. values are short_name keys above.
EXTERNAL_REFERENCE_ALIASES: Dict[str, str] = {
    "Paris Convention": "paris",
    "Berne Convention": "berne",
    "Madrid Agreement": "madrid-marks",
    "Hague Agreement": "hague",
    "Nice Agreement": "nice",
    "Lisbon Agreement": "lisbon",
    "Rome Convention": "rome",
    "WIPO Convention": "wipo-convention",
    "Convention Establishing the World Intellectual Property Organization": "wipo-convention",
    "Locarno Agreement": "locarno",
    "Patent Cooperation Treaty": "pct",
    "PCT": "pct",
    "Geneva Phonograms Convention": "phonograms",
    "Phonograms Convention": "phonograms",
    "Strasbourg Agreement": "strasbourg",
    "Vienna Agreement": "vienna",
    "Brussels Convention": "brussels",
    "Budapest Treaty": "budapest",
    "Nairobi Treaty": "nairobi",
    "Madrid Protocol": "madrid-protocol",
    "Washington IPIC Treaty": "washington",
    "Washington Treaty": "washington",
    "Trademark Law Treaty": "tlt",
    "TLT": "tlt",
    "WCT": "wct",
    "WIPO Copyright Treaty": "wct",
    "WPPT": "wppt",
    "WIPO Performances and Phonograms Treaty": "wppt",
    "Patent Law Treaty": "plt",
    "PLT": "plt",
    "Singapore Treaty": "singapore",
    "Beijing Treaty": "beijing",
    "Marrakesh Treaty": "marrakesh",
    "WIPO GRATK Treaty": "gratk",
    "GRATK Treaty": "gratk",
    "Riyadh Treaty": "rdlt",
    "Riyadh Design Law Treaty": "rdlt",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_space(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = text.replace("\u2009", " ")
    text = text.replace("\u202f", " ")
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_compare(text: str) -> str:
    return normalize_space(text).lower()


def make_slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def canonical_article_token(raw_token: str) -> str:
    token = normalize_space(raw_token).replace(" ", "").lower()
    token = token.replace(".", "")
    return token


def canonical_marker_token(raw_token: str) -> str:
    token = normalize_space(raw_token)
    token = token.strip("()")
    token = token.strip(".")
    token = token.strip()
    token = token.lower()
    token = token.replace(" ", "")
    token = token.replace(".", "_")
    token = token.replace("(", "_")
    token = token.replace(")", "")
    token = token.replace("/", "_")
    token = re.sub(r"[^a-z0-9_-]+", "", token)
    token = re.sub(r"_+", "_", token)
    return token.strip("_")


def marker_sort_key(token: str) -> Tuple[int, str]:
    if token.isdigit():
        return (0, token)
    return (1, token)


def is_roman(token: str) -> bool:
    return bool(token) and bool(re.fullmatch(r"[ivxlcdm]+", token.lower()))


def extract_date_from_text(*chunks: str, fallback_year: int) -> str:
    text = normalize_space(" ".join(chunks))
    date_match = re.search(
        r"\b(" + "|".join(MONTHS.keys()) + r")\s+(\d{1,2}),\s*(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    if date_match:
        month = MONTHS[date_match.group(1).lower()]
        day = int(date_match.group(2))
        year = int(date_match.group(3))
        try:
            return _dt.date(year, month, day).isoformat()
        except ValueError:
            pass

    year_match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", text)
    if year_match:
        year = int(year_match.group(1))
        return f"{year:04d}-01-01"

    return f"{fallback_year:04d}-01-01"


def today_iso() -> str:
    return _dt.date.today().isoformat()


def output_file_name(year: int, short_name: str) -> str:
    return f"{year:04d}_{short_name}_clean.xml"


def compare_similarity(source_text: str, target_text: str) -> float:
    src = normalize_for_compare(source_text)
    tgt = normalize_for_compare(target_text)
    if not src and not tgt:
        return 1.0
    if not src or not tgt:
        return 0.0
    return SequenceMatcher(None, src, tgt).ratio()


def json_dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_text_list(lines: Iterable[str]) -> List[str]:
    out: List[str] = []
    for line in lines:
        txt = normalize_space(line)
        if txt:
            out.append(txt)
    return out


def looks_like_date_line(text: str) -> bool:
    lowered = text.lower()
    if re.match(r"^(of|adopted|signed|concluded|done)\b", lowered):
        return True
    if "amended on" in lowered and len(text) < 200:
        return True
    if re.match(r"^\(.*\)$", text) and any(m in lowered for m in MONTHS):
        return True
    return False


def looks_like_toc_heading(text: str) -> bool:
    lowered = text.lower()
    return (
        "table of contents" in lowered
        or "list of the articles" in lowered
        or "list of articles" in lowered
        or "contents" == lowered
        or lowered.startswith("table of content")
    )


def looks_like_editorial_note(text: str) -> bool:
    lowered = text.lower()
    if "this table of contents is added for the convenience" in lowered:
        return True
    if "editor's note" in lowered or "editor’s note" in lowered:
        return True
    if "new contribution system" in lowered:
        return True
    if lowered in {"* *", "*"}:
        return True
    return False


def build_work_iri(subtype: str, date_iso: str, short_name: str) -> str:
    return f"/akn/un/act/{subtype}/wipo/{date_iso}/{short_name}"


def article_ref_to_eid(article_token: str, para_token: Optional[str] = None) -> str:
    art = canonical_article_token(article_token)
    if para_token is None:
        return f"art_{art}"
    para = canonical_marker_token(para_token)
    return f"art_{art}__para_{para}"


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
