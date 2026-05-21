# A Neuro-Symbolic System for Querying and Monitoring Copyright Compliance Across National Legislations

**Authors:** Brüne, Corazza, Longo, Sapienza, Vagnoni  
**Supervisor:** Prof. Monica Palmirani  
**Venue:** IRIS 2026 Hackathon

---

## Abstract

We present a neuro-symbolic web application for querying intellectual property law across multiple national jurisdictions and checking their compliance with WIPO treaty obligations. The system combines a large language model (LLM) for multilingual query enrichment and answer generation with a symbolic pipeline composed of an RDF Knowledge Graph built over Akoma Ntoso (AKN) legal documents, SPARQL-based retrieval, and a structured compliance checker grounded in the IPROnto ontology. Users can ask questions in any language and receive answers grounded in the source legal text, or inspect whether a given country meets the minimum copyright duration mandated by the Berne Convention. We describe the architecture, report on what works in the current prototype, and identify the key gaps toward a production-grade bidirectional compliance monitoring system.

---

## 1. Introduction

The monitoring of national legislation with respect to international IP treaties — and vice versa — is a labor-intensive legal task. A jurist wishing to answer "Is Italy compliant with Berne Convention Art. 7 on copyright duration?" must locate the relevant provision in the Italian Copyright Act, extract the normative value (e.g., 70 years post-mortem auctoris), and compare it semantically with the treaty minimum (50 years). Repeating this across the 9+ jurisdictions covered by WIPO requires systematic, machine-readable representations of legal norms.

Recent advances in Large Language Models (LLMs) offer fluent natural-language understanding and generation but lack grounding in authoritative legal sources and are prone to hallucination. Symbolic Knowledge Graphs (KGs) encode structured facts precisely but cannot handle the ambiguity and multilingualism of user queries. We argue that a **neuro-symbolic** integration — LLM for understanding, KG for retrieval and reasoning — is the appropriate architecture for this task.

This paper presents a minimum viable prototype (MVP) developed during the IRIS 2026 Hackathon. The goal of the hackathon was to demonstrate the feasibility of the neuro-symbolic approach within a constrained timeframe, not to deliver a production system. The prototype supports two interaction modes: (1) a **Q&A chatbot** that retrieves relevant legal provisions from an AKN-based KG and generates grounded answers via LLM; and (2) a **compliance checker** that queries the KG for a country's copyright duration, compares it against the WIPO Berne Convention minimum using integer-typed RDF triples, and produces a structured verdict. Known limitations — in particular the absence of temporal modeling and the small scale of the dataset — are discussed in Section 6.

---

## 2. Background and Related Work

### 2.1 Akoma Ntoso

Akoma Ntoso (AKN) is an OASIS standard for the XML representation of legal and parliamentary documents. It provides a hierarchical structure of `<act>`, `<body>`, `<section>`, `<article>`, and `<paragraph>` elements, each identified by a stable `eId` attribute. We use AKN documents as the authoritative source for nine jurisdictions: Germany, France, Italy, Switzerland, United Kingdom, United States, Canada, New Zealand, and the European Union.

### 2.2 IPROnto

IPROnto is an OWL ontology for the intellectual property domain, developed by the Distributed Multimedia Applications Group (DMAG) at the Universitat Politècnica de Catalunya (Delgado et al., 2003). It defines classes such as `ExploitationRight`, `ExceptionsRight`, and properties for jurisdiction, duration, and rights grants. We use the IPROnto namespace (`http://rhizomik.net/ontologies/2005/03/ipronto.owl#`) as the backbone of our RDF Knowledge Graph, extending it with `legal:` properties for SPARQL querying.

### 2.3 Neuro-Symbolic Legal AI

The combination of neural and symbolic methods for legal reasoning has been explored in [cite: Palmirani et al., LegalRuleML; Nardi et al., 2026 ontology analysis]. Our contribution is a working end-to-end pipeline that connects LLM-based query enrichment directly to SPARQL retrieval over AKN-grounded KG triples, without requiring manual query formulation by the user.

---

## 3. System Architecture

The proposed pipeline consists of four stages.

### 3.1 Task 1 — Multilingual Query Enrichment (Neural)

The user's natural-language question — in any language — is passed to a large language model (Google Gemini 2.0 Flash via the OpenRouter API) with a structured system prompt. The LLM returns a JSON object with four fields:

- `Jurisdiction`: one of 9 country names or "WIPO" / "Unknown"
- `Legal_Topic`: one of "copyright duration", "economic rights", "personal-use exception", or "intellectual property"
- `Time_Frame`: year range or "Current"
- `User_Objective`: one-sentence English rephrasing

This step is entirely neural and handles multilingual input natively (e.g., Italian "quando scade il diritto d'autore in Francia?" is correctly mapped to Jurisdiction=France, Legal_Topic=copyright duration).

### 3.2 KG Retrieval (Symbolic — SPARQL)

The enriched context is passed to a Pydantic model (`SPARQLParams`) that normalises jurisdiction codes and rule types, then used to generate one of three SPARQL SELECT templates (duration, economic rights, exception). The query executes against an in-memory rdflib graph, loaded lazily on first request from a serialised RDF/Turtle file and cached for subsequent calls. When the jurisdiction is unknown or maps to WIPO, the system falls back to a pre-populated evidence record derived from Berne Convention reference data.

The KG triples follow the pattern:

```turtle
ex:CH_duration a ipronto:ExploitationRight ;
    legal:jurisdiction      "CH" ;
    legal:jurisdictionName  "Switzerland" ;
    legal:ruleType          "copyright duration" ;
    legal:durationLiterary  "70 years pma" ;
    legal:durationYears     70 ;           # xsd:integer
    ipronto:triggeredBy     "death of author" ;
    legal:articleRef        "Art. 29 URG" ;
    legal:compliesWith      ex:WIPO_berne_art7 .

ex:WIPO_berne_art7 a ipronto:ExploitationRight ;
    legal:jurisdiction    "WIPO" ;
    legal:durationYears   50 ;
    legal:articleRef      "Art. 7 Berne Convention" .
```

The `legal:durationYears` integer property enables numeric compliance comparison without string parsing at query time.

### 3.3 AKN Passage Extraction (Symbolic)

The article reference retrieved from the KG (e.g., "Art. 29 URG") is resolved to an AKN `eId` (e.g., `art_29`) by the ArticleLocator module, which walks the parsed XML tree looking for `<num>` elements whose normalised text matches the reference. This step runs at query time against the AKN XML files, which are accessed directly and are not part of the KG build. The corresponding AKN element is then rendered as HTML with yellow highlighting of the supporting span. The user sees the original legal text in context, not a paraphrase.

### 3.4 Answer Generation (Neural)

The KG evidence (answer candidate, passage, article reference, document title) and the enriched context are serialised as JSON and passed to the same LLM with a grounding-focused system prompt: "Give a 2–4 sentence answer strictly grounded in the evidence; cite the article at the end; if no evidence is found, say so." This produces answers that are traceable back to the source provision.

### 3.5 Compliance Checker

The compliance checker is a pure symbolic module. Given a country code, it fetches the `legal:durationYears` integer from the country's KG duration node and from `ex:WIPO_berne_art7`, compares them, and computes a margin. It returns a structured result rendered in the UI as a side-by-side comparison card (country duration vs. treaty minimum, verdict, margin in years). No LLM is involved.

---

## 4. Implementation

The system is a Flask web application with two UI modes accessible via tab switching. The left panel hosts either the Q&A chatbot or the compliance checker form; the right panel is a document viewer shared between both modes.

Key technology choices:

| Component | Technology |
|---|---|
| Web framework | Flask (Python) |
| KG store | rdflib (in-memory, TTL serialisation) |
| XML parsing | lxml |
| LLM API | OpenRouter (Gemini 2.0 Flash) |
| Schema validation | Pydantic v2 |
| Legal documents | AKN XML (9 jurisdictions) |
| Ontology | IPROnto OWL namespace |

The KG is built from a curated CSV dataset (9 rows, one per jurisdiction) on first request and cached in memory for subsequent calls. The AKN XML files are accessed separately at query time and are not ingested into the KG. Total triples: 446.

---

## 5. What Works

- **Multilingual Q&A**: questions in Italian, English, French, German are correctly enriched and routed to the right jurisdiction and rule type.
- **SPARQL retrieval**: all three rule types (duration, economic rights, personal-use exception) return correct KG evidence for all 9 jurisdictions.
- **AKN passage extraction**: source articles are located and rendered for Swiss (URG Art. 29), German (UrhG §§ 15, 64), Italian (LDA Art. 12, 25), and other AKN documents. Both `<article>` (Swiss) and `<section>` (German) leaf provision types are handled.
- **Compliance checking**: the Berne Convention Art. 7 compliance check works for all 9 countries. New Zealand (50 years, exactly at minimum) and all 70-year jurisdictions are correctly classified.
- **Grounded answers**: the LLM answer always cites the article reference and is derived from the extracted KG passage, not from LLM parametric memory.

---

## 6. Limitations and Future Work

### 6.1 Temporal Compliance Modeling

The central vision of this work — "Was Austria compliant with the Marrakesh Treaty on February 20, 2019?" — requires temporal modeling. The current KG has no `valid_from` / `valid_until` timestamps on triples. Adding temporal validity intervals to each provision node and implementing SPARQL queries that filter by date is the most impactful missing piece. We plan to address this using the RDF-star temporal extension and integrating WIPO treaty entry-into-force metadata as structured KG nodes.

### 6.2 Bidirectional Monitoring

The current implementation covers only **national → treaty** compliance (does country X meet treaty minimum Y?). The other direction — **treaty → national** ("which countries have not yet transposed Directive X?") — requires knowing each country's transposition deadline, which is not in the current dataset.

### 6.3 Semantic Equivalence Reasoning

The Berne minimum is "at least 50 years". Our integer comparison (`70 >= 50`) captures this correctly for duration, but semantic compliance for other rights (e.g., "Does country X's communication right cover what WIPO means by 'making available'?") requires OWL reasoning over the IPROnto class hierarchy, not just numeric comparison.

### 6.4 KG Scale and Automation

The current dataset covers 3 rule types × 9 jurisdictions = 27 core nodes. A production system would need to automatically parse and ingest AKN documents into KG triples (currently done manually via CSV), cover all IP rights dimensions defined in IPROnto, and integrate with live legislative sources (EUR-Lex, national gazette APIs).

### 6.5 eId-Based Subject URIs

Subject URIs currently follow the pattern `ex:CH_duration` rather than the target pattern `ex:CH_art_29`. Embedding the eId into the URI would allow SPARQL queries that directly dereference to the AKN provision, eliminating the ArticleLocator lookup at query time.

### 6.6 No OWL Reasoning

The KG uses RDF triples only. The IPROnto OWL axioms (class hierarchy, domain/range restrictions) are not exploited. Adding a reasoner (e.g., OWL-RL via owlrl) would enable inference over the class hierarchy: e.g., inferring that a `ReproductionRight` is an `ExploitationRight` without explicit typing.

---

## 7. Conclusion

This MVP demonstrates that a neuro-symbolic pipeline — LLM for query understanding and answer generation, SPARQL+RDF for structured retrieval, AKN XML for source grounding — is a viable approach for legal IP compliance monitoring, and that its core components can be integrated and validated within the timeframe of a hackathon. The compliance checker, grounded in integer-typed KG triples and `ipronto:compliesWith` links, shows that the symbolic layer can answer structured compliance questions without any LLM involvement, reducing latency and hallucination risk for that query type. The limitations described in Section 6 — temporal modeling, bidirectional monitoring, OWL reasoning, KG scale — constitute the roadmap from this hackathon prototype toward a production-grade system.

---

## References

- Palmirani, M. et al. LegalRuleML: Making XML Smart for Legal Rule Markup. In *Legal Knowledge and Information Systems*, IOS Press.
- Nardi, D. et al. (2026). An Analysis of Ontologies for the Intellectual Property Domain. *(in this volume)*
- OASIS. Akoma Ntoso Version 1.0. OASIS Standard, 2018.
<<<<<<< HEAD
- Delgado, J. et al. (2003). IPROnto: Intellectual Property Rights Ontology. https://dmag.ac.upc.edu/ontologies/ipronto/ipronto.owl .
=======
- García, R. et al. IPROnto: An Ontology for Digital Rights Management. Distributed Multimedia Applications Group (DMAG), Universitat Politècnica de Catalunya, 2001. http://dmag.ac.upc.edu/ontologies/ipronto.owl
>>>>>>> 3c64e16 (Update architecture diagram and fix paper inaccuracies)
- Berne Convention for the Protection of Literary and Artistic Works, Art. 7. WIPO, 1886 (as amended 1979).
- OpenRouter. Unified LLM API. https://openrouter.ai (2024).
