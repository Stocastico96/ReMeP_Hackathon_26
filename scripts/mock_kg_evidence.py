"""Mock evidence payload standing in for Generoso's KG agent.

Replace ``get_mock_evidence`` with a real call to the KG agent once it is
available.  The return type and field names must stay stable — Task 2 and
Task 3 depend on them.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class NormalizedRule(TypedDict, total=False):
    value: str
    unit: str


class DocumentRef(TypedDict, total=False):
    title: str
    uri: str
    local_path: str
    source_url: str      # publisher's web page — a locator, unlike the FRBR URIs


class AKNReference(TypedDict, total=False):
    article: str
    paragraph: str
    eid: str


class KGEvidence(TypedDict, total=False):
    answer_candidate: str
    rule_type: str
    normalized_rule: NormalizedRule
    document: DocumentRef
    reference: AKNReference
    passage: str
    supporting_span: str


# ---------------------------------------------------------------------------
# Mock payloads — one per (rule_type, jurisdiction) scenario
# ---------------------------------------------------------------------------

_MOCK: dict[tuple[str, str], KGEvidence] = {
    # Q1 — copyright duration ------------------------------------------------
    ("copyright duration", "Switzerland"): {
        "answer_candidate": "Copyright protection lasts for 70 years after the death of the author.",
        "rule_type": "copyright duration",
        "normalized_rule": {"value": "life_plus_70", "unit": "years"},
        "document": {
            "title": "Swiss Copyright Act (URG)",
            "uri": "data/countries/switzerland/copyright/urg_copyright_act.xml",
            "local_path": "data/countries/switzerland/copyright/urg_copyright_act.xml",
        },
        "reference": {"article": "Article 29", "paragraph": "2", "eid": "art_29__para_2"},
        "passage": "Protection expires 70 years after the death of the author.",
        "supporting_span": "70 years after the death of the author",
    },
    ("copyright duration", "Germany"): {
        "answer_candidate": "Copyright protection expires 70 years after the death of the author.",
        "rule_type": "copyright duration",
        "normalized_rule": {"value": "life_plus_70", "unit": "years"},
        "document": {
            "title": "German Copyright Act (UrhG)",
            "uri": "data/countries/germany/copyright/urhg_copyright_act.xml",
            "local_path": "data/countries/germany/copyright/urhg_copyright_act.xml",
        },
        "reference": {"article": "§ 64", "eid": "sec_64"},
        "passage": "The copyright expires seventy years after the death of the author.",
        "supporting_span": "seventy years after the death of the author",
    },
    ("copyright duration", "France"): {
        "answer_candidate": "Copyright protection lasts for 70 years after the death of the author.",
        "rule_type": "copyright duration",
        "normalized_rule": {"value": "life_plus_70", "unit": "years"},
        "document": {
            "title": "French Intellectual Property Code (CPI)",
            "uri": "data/countries/france/copyright/cpi_copyright_act.xml",
            "local_path": "data/countries/france/copyright/cpi_copyright_act.xml",
        },
        "reference": {"article": "Article L. 123-1", "eid": "art_L123-1"},
        "passage": "The author shall enjoy, during his lifetime, the exclusive right to exploit his work in any form whatsoever. After his death this right shall persist for the benefit of his successors in title during the current calendar year and the seventy years thereafter.",
        "supporting_span": "seventy years thereafter",
    },
    ("copyright duration", "United Kingdom"): {
        "answer_candidate": "Copyright expires 70 years from the end of the calendar year in which the author dies.",
        "rule_type": "copyright duration",
        "normalized_rule": {"value": "life_plus_70", "unit": "years"},
        "document": {
            "title": "Copyright, Designs and Patents Act 1988 (CDPA)",
            "uri": "data/countries/uk/copyright/cdpa_1988.xml",
            "local_path": "data/countries/uk/copyright/cdpa_1988.xml",
        },
        "reference": {"article": "Section 12", "paragraph": "1", "eid": "sec_12__para_1"},
        "passage": "Copyright in a literary, dramatic, musical or artistic work expires at the end of the period of 70 years from the end of the calendar year in which the author dies.",
        "supporting_span": "70 years from the end of the calendar year in which the author dies",
    },
    ("copyright duration", "WIPO"): {
        "answer_candidate": "The Berne Convention sets a minimum copyright term of the life of the author plus 50 years.",
        "rule_type": "copyright duration",
        "normalized_rule": {"value": "life_plus_50", "unit": "years"},
        "document": {
            "title": "Berne Convention for the Protection of Literary and Artistic Works",
            "uri": "/akn/un/act/convention/wipo/1886-09-09/berne",
            "local_path": "data/wipo/akns_enriched/1886_berne_clean.xml",
        },
        "reference": {"article": "Article 7", "paragraph": "1", "eid": "art_7__para_1"},
        "passage": "The term of protection granted by this Convention shall be the life of the author and fifty years after his death.",
        "supporting_span": "the life of the author and fifty years after his death",
    },
    # Q2 — economic rights ---------------------------------------------------
    ("economic rights", "France"): {
        "answer_candidate": "France recognises the rights of reproduction, public performance, and communication to the public.",
        "rule_type": "economic rights",
        "normalized_rule": {"value": "list"},
        "document": {
            "title": "French Intellectual Property Code (CPI)",
            "uri": "data/countries/france/copyright/cpi_copyright_act.xml",
            "local_path": "data/countries/france/copyright/cpi_copyright_act.xml",
        },
        "reference": {"article": "Article L. 122-1", "eid": "art_L122-1"},
        "passage": "The right of exploitation belonging to the author shall comprise the right of representation and the right of reproduction.",
        "supporting_span": "the right of representation and the right of reproduction",
    },
    ("economic rights", "Germany"): {
        "answer_candidate": "Germany recognises reproduction, distribution, exhibition, public rendition, broadcasting, and making available to the public.",
        "rule_type": "economic rights",
        "normalized_rule": {"value": "list"},
        "document": {
            "title": "German Copyright Act (UrhG)",
            "uri": "data/countries/germany/copyright/urhg_copyright_act.xml",
            "local_path": "data/countries/germany/copyright/urhg_copyright_act.xml",
        },
        "reference": {"article": "§ 15", "eid": "sec_15"},
        "passage": "The author shall have the exclusive right to exploit his work in any corporeal form; the right shall include in particular the reproduction right, the distribution right, and the exhibition right.",
        "supporting_span": "the reproduction right, the distribution right, and the exhibition right",
    },
    ("economic rights", "WIPO"): {
        "answer_candidate": "The Berne Convention recognises the right of reproduction, translation, adaptation, and communication to the public.",
        "rule_type": "economic rights",
        "normalized_rule": {"value": "list"},
        "document": {
            "title": "Berne Convention for the Protection of Literary and Artistic Works",
            "uri": "/akn/un/act/convention/wipo/1886-09-09/berne",
            "local_path": "data/wipo/akns_enriched/1886_berne_clean.xml",
        },
        "reference": {"article": "Article 9", "paragraph": "1", "eid": "art_9__para_1"},
        "passage": "Authors of literary and artistic works protected by this Convention shall have the exclusive right of authorizing the reproduction of these works, in any manner or form.",
        "supporting_span": "the exclusive right of authorizing the reproduction of these works, in any manner or form",
    },
    # Q3 — personal-use exception --------------------------------------------
    ("personal-use exception", "Germany"): {
        "answer_candidate": "Yes, Germany provides a private-copy exception for reproductions made for personal use.",
        "rule_type": "personal-use exception",
        "normalized_rule": {"value": "yes"},
        "document": {
            "title": "German Copyright Act (UrhG)",
            "uri": "data/countries/germany/copyright/urhg_copyright_act.xml",
            "local_path": "data/countries/germany/copyright/urhg_copyright_act.xml",
        },
        "reference": {"article": "§ 53", "paragraph": "1", "eid": "sec_53__para_1"},
        "passage": "It is permissible to make single copies of a work for private use on any medium, insofar as this is not done for commercial purposes and as long as the original has not been reproduced by an obviously unlawful copy.",
        "supporting_span": "permissible to make single copies of a work for private use",
    },
    ("personal-use exception", "Italy"): {
        "answer_candidate": "Yes, Italy provides a private-copy exception limited to personal use and non-commercial purposes.",
        "rule_type": "personal-use exception",
        "normalized_rule": {"value": "yes"},
        "document": {
            "title": "Italian Copyright Act (LDA)",
            "uri": "data/countries/italy/copyright/19410716_041U0633_VIGENZA_20251218.xml",
            "local_path": "data/countries/italy/copyright/19410716_041U0633_VIGENZA_20251218.xml",
        },
        "reference": {"article": "Article 71-sexies", "paragraph": "1", "eid": "art_71-sexies__para_1"},
        "passage": "La riproduzione di fonogrammi e videogrammi su qualsiasi supporto è consentita all'utente a fini esclusivamente personali.",
        "supporting_span": "consentita all'utente a fini esclusivamente personali",
    },
    ("personal-use exception", "Switzerland"): {
        "answer_candidate": "Yes, Switzerland allows private copying for personal use within the private sphere.",
        "rule_type": "personal-use exception",
        "normalized_rule": {"value": "yes"},
        "document": {
            "title": "Swiss Copyright Act (URG)",
            "uri": "data/countries/switzerland/copyright/urg_copyright_act.xml",
            "local_path": "data/countries/switzerland/copyright/urg_copyright_act.xml",
        },
        "reference": {"article": "Article 19", "paragraph": "1", "eid": "art_19__para_1"},
        "passage": "Published works may be used for personal use. Personal use means any private use of a work for personal purposes or within a circle of persons closely connected to each other.",
        "supporting_span": "any private use of a work for personal purposes or within a circle of persons closely connected to each other",
    },
}


def get_mock_evidence(rule_type: str, jurisdiction: str) -> KGEvidence:
    """Return a mock KG evidence payload.

    Args:
        rule_type:   One of the Legal_Topic values from the enriched context
                     (e.g. "copyright duration", "economic rights",
                     "personal-use exception").
        jurisdiction: Jurisdiction string from the enriched context
                      (e.g. "Switzerland", "Germany", "WIPO").

    Returns:
        A KGEvidence dict.  When Generoso's agent is ready, replace this
        function body with the real call and keep the signature.
    """
    key = (rule_type, jurisdiction)
    if key in _MOCK:
        return _MOCK[key]

    # Fallback: nearest rule_type match regardless of jurisdiction
    for (rt, _), evidence in _MOCK.items():
        if rt == rule_type:
            return evidence

    # Last resort
    return {
        "answer_candidate": "",
        "rule_type": rule_type,
        "normalized_rule": {},
        "document": {"title": "", "uri": "", "local_path": ""},
        "reference": {},
        "passage": "",
        "supporting_span": "",
    }
