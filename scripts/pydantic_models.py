"""Pydantic v2 models for the KG retrieval pipeline."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


JURISDICTION_CODE: dict[str, str] = {
    "Canada":         "CA",
    "EU":             "EU",
    "France":         "FR",
    "Germany":        "DE",
    "Italy":          "IT",
    "New Zealand":    "NZ",
    "Switzerland":    "CH",
    "United Kingdom": "UK",
    "United States":  "US",
    "WIPO":           "WIPO",
    "Unknown":        "",
}

RULE_TYPE_KEY: dict[str, str] = {
    "copyright duration":    "duration",
    "economic rights":       "rights",
    "personal-use exception": "exception",
}


class SPARQLParams(BaseModel):
    """Validated parameters for generating a SPARQL query over the legal KG."""

    jurisdiction_name: str = Field(description="Full jurisdiction name from enriched context")
    jurisdiction_code: str = Field(default="", description="ISO/short code derived from name")
    rule_type: str = Field(description="Legal topic: 'copyright duration', 'economic rights', etc.")
    rule_key: str = Field(default="", description="Short key for the rule type")

    @model_validator(mode="after")
    def _derive_codes(self) -> "SPARQLParams":
        if not self.jurisdiction_code:
            self.jurisdiction_code = JURISDICTION_CODE.get(self.jurisdiction_name, "")
        if not self.rule_key:
            self.rule_key = RULE_TYPE_KEY.get(self.rule_type, "")
        return self

    @classmethod
    def from_enriched(cls, extracted_context: dict) -> "SPARQLParams":
        return cls(
            jurisdiction_name=extracted_context.get("Jurisdiction", "Unknown"),
            rule_type=extracted_context.get("Legal_Topic", "copyright"),
        )
