"""Extract FRBR/ELI metadata from Akoma Ntoso documents.

Provides authentic source URIs and point-in-time applicability dates
for each legal document in the corpus.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_NS    = {"akn": AKN_NS}

# Date attribute names used across different AKN corpora
_APPLICABILITY_NAMES = {"dateapplicability", "applicability"}
_FORCE_NAMES         = {"dateentryinforce", "entryinforce", "force", "enactment", "enacted"}


def extract_frbr(local_path: str) -> dict:
    """Return FRBR/ELI metadata extracted from the AKN document at *local_path*.

    Keys:
        frbr_work_uri   — canonical Work-level URI (authoritative identifier)
        frbr_this       — the FRBRthis expression URI (most specific pointer)
        eli_uri         — ELI URI if present (e.g. Italian NormeInRete)
        point_in_time   — date this version is applicable (ISO 8601 or "")
        date_in_force   — date the law entered into force (ISO 8601 or "")
        is_authoritative — True if FRBRauthoritative or FRBRprescriptive is "true"
        country         — ISO country code from FRBRcountry
    """
    path = Path(local_path)
    if not path.exists():
        return _empty()
    try:
        return _parse(path)
    except Exception:
        return _empty()


@lru_cache(maxsize=16)
def _parse(path: Path) -> dict:
    root = etree.parse(str(path)).getroot()

    work  = root.find(".//akn:FRBRWork", _NS)
    if work is None:
        return _empty()

    frbr_uri  = _val(work, "akn:FRBRuri")
    frbr_this = _val(work, "akn:FRBRthis")
    country   = _val(work, "akn:FRBRcountry")

    # Point-in-time: prefer dateApplicability, fall back to enacted/enactment date
    pit   = ""
    eif   = ""
    for date_el in work.findall("akn:FRBRdate", _NS):
        name = date_el.get("name", "").lower().replace("jolux:", "").replace(":", "")
        val  = date_el.get("date", "")
        if name in _APPLICABILITY_NAMES and not pit:
            pit = val
        if name in _FORCE_NAMES and not eif:
            eif = val
    # AKN puts the version date on the Expression, not the Work (the Work date is
    # the original enactment), so prefer an applicability date found there.
    expr = root.find(".//akn:FRBRExpression", _NS)
    if expr is not None:
        for date_el in expr.findall("akn:FRBRdate", _NS):
            name = date_el.get("name", "").lower().replace("jolux:", "").replace(":", "")
            if name in _APPLICABILITY_NAMES:
                pit = date_el.get("date", "") or pit
                break

    # If no applicability date found, use entry-in-force as best proxy
    if not pit:
        pit = eif

    # ELI alias (Italian NormeInRete, etc.) and the publisher's own web address.
    # The latter is a locator, unlike the FRBR URIs, so it is the only value that
    # may be handed to a browser as a link.
    eli = ""
    source_uri = ""
    for alias in work.findall("akn:FRBRalias", _NS):
        name = alias.get("name", "").lower()
        if name in ("eli", "urn:eli") and not eli:
            eli = alias.get("value", "")
        if name in ("sourceuri", "sourceurl") and not source_uri:
            source_uri = alias.get("value", "")

    # Authenticity markers
    auth_el = work.find("akn:FRBRauthoritative", _NS)
    presc_el = work.find("akn:FRBRprescriptive", _NS)
    is_auth = (
        (auth_el  is not None and auth_el.get("value",  "").lower() == "true") or
        (presc_el is not None and presc_el.get("value", "").lower() == "true")
    )

    return {
        "frbr_work_uri":   frbr_uri,
        "frbr_this":       frbr_this,
        "eli_uri":         eli,
        "source_uri":      source_uri,
        "point_in_time":   pit,
        "date_in_force":   eif,
        "is_authoritative": is_auth,
        "country":         country,
    }


def _val(parent, xpath: str) -> str:
    el = parent.find(xpath, _NS)
    return el.get("value", "") if el is not None else ""


def _empty() -> dict:
    return {
        "frbr_work_uri":   "",
        "frbr_this":       "",
        "eli_uri":         "",
        "source_uri":      "",
        "point_in_time":   "",
        "date_in_force":   "",
        "is_authoritative": False,
        "country":         "",
    }
