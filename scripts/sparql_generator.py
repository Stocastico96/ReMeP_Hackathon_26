"""Generate SPARQL SELECT queries from validated SPARQLParams.

Each rule type gets its own query template, parameterized by jurisdiction code.
"""

from __future__ import annotations

from scripts.pydantic_models import SPARQLParams

PREFIXES = """\
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ipronto: <http://rhizomik.net/ontologies/2005/03/ipronto.owl#>
PREFIX legal:  <http://legal-kg.org/schema/>
PREFIX ex:     <http://legal-kg.org/data/>
"""


def generate_sparql(params: SPARQLParams) -> str:
    """Return a SPARQL SELECT string for the given validated parameters."""
    if params.rule_type == "copyright duration":
        return _duration_query(params)
    if params.rule_type == "economic rights":
        return _rights_query(params)
    if params.rule_type == "personal-use exception":
        return _exception_query(params)
    # Fallback: generic duration query
    return _duration_query(params)


def _duration_query(params: SPARQLParams) -> str:
    code = params.jurisdiction_code
    if code:
        filter_clause = f'FILTER(?jurisdiction = "{code}")'
    else:
        # Unknown jurisdiction — return all, caller picks first
        filter_clause = ""
    return f"""{PREFIXES}
SELECT ?node ?jurisdictionName ?durationLiterary ?durationSoftware ?articleRef ?localPath ?docTitle
WHERE {{
  ?node rdf:type ipronto:ExploitationRight ;
        legal:ruleType "copyright duration" ;
        legal:jurisdiction ?jurisdiction ;
        legal:jurisdictionName ?jurisdictionName ;
        legal:durationLiterary ?durationLiterary ;
        legal:durationSoftware ?durationSoftware ;
        legal:localPath ?localPath ;
        legal:docTitle ?docTitle .
  OPTIONAL {{ ?node legal:articleRef ?articleRef }}
  {filter_clause}
}}
"""


def _rights_query(params: SPARQLParams) -> str:
    code = params.jurisdiction_code
    filter_clause = f'FILTER(?jurisdiction = "{code}")' if code else ""
    return f"""{PREFIXES}
SELECT ?node ?jurisdictionName ?right ?articleRef ?localPath ?docTitle ?rightsNote
WHERE {{
  ?node rdf:type ipronto:ExploitationRight ;
        legal:ruleType "economic rights" ;
        legal:jurisdiction ?jurisdiction ;
        legal:jurisdictionName ?jurisdictionName ;
        legal:hasRight ?right ;
        legal:localPath ?localPath ;
        legal:docTitle ?docTitle .
  OPTIONAL {{ ?node legal:articleRef ?articleRef }}
  OPTIONAL {{ ?node legal:rightsNote ?rightsNote }}
  {filter_clause}
}}
ORDER BY ?right
"""


def _exception_query(params: SPARQLParams) -> str:
    code = params.jurisdiction_code
    filter_clause = f'FILTER(?jurisdiction = "{code}")' if code else ""
    return f"""{PREFIXES}
SELECT ?node ?jurisdictionName ?hasException ?exceptionText ?articleRef ?localPath ?docTitle
WHERE {{
  ?node rdf:type ipronto:ExceptionsRight ;
        legal:ruleType "personal-use exception" ;
        legal:jurisdiction ?jurisdiction ;
        legal:jurisdictionName ?jurisdictionName ;
        legal:hasException ?hasException ;
        legal:exceptionText ?exceptionText ;
        legal:localPath ?localPath ;
        legal:docTitle ?docTitle .
  OPTIONAL {{ ?node legal:articleRef ?articleRef }}
  {filter_clause}
}}
"""
