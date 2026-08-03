# A Neuro-Symbolic System for Querying and Monitoring Copyright Compliance Across National Legislations

Built for the IRIS 2026 Hackathon by Brüne, Corazza, Longo, Sapienza, and Vagnoni, supervised by Prof. Monica Palmirani.

Checking whether a country's copyright law actually lines up with its WIPO treaty obligations is still mostly manual work. A lawyer has to track down the right provision, read off the number of years, and hold it against the treaty floor. Doing that for one country is tedious; doing it for nine is slow and easy to get wrong. We wanted to see how far we could automate it without letting a language model anywhere near the numbers a verdict depends on.

## How it works

The system has two halves that play to their respective strengths. A neural layer (an LLM) handles the messy, multilingual side: understanding a question phrased in German or French and writing the final answer in plain language. A symbolic layer does the part that has to be exact, running SPARQL queries over an RDF knowledge graph built from Akoma Ntoso legal documents and the IPROnto ontology. The compliance decision itself never touches the LLM.

![System architecture diagram](MVP_proposal_diagram.png)

## What you can do with it

There are two modes.

In **Q&A mode** you ask a question in any language about intellectual property law. The system enriches the query, pulls the relevant provision out of the knowledge graph, extracts the actual passage from the source AKN XML, and gives you a grounded answer that cites the article. The source document is shown alongside, with the relevant article highlighted.

<img width="818" height="683" alt="Q&A mode" src="https://github.com/user-attachments/assets/bd69ca29-72ce-4193-af89-a93dcb7425a2" />

In **Compliance Check mode** you pick a country and the system verifies whether its copyright duration meets the Berne Convention minimum (Article 7, 50 years post mortem). This part is purely symbolic, no LLM in the loop, so the answer is reproducible and traceable straight back to the encoded facts.

<img width="822" height="685" alt="Compliance Check mode" src="https://github.com/user-attachments/assets/7cf5c1e0-31df-49c9-8d45-14a72ad98a72" />

We covered nine jurisdictions: Germany, France, Italy, Switzerland, the United Kingdom, the United States, Canada, New Zealand, and the European Union.

## Running it locally

You'll need an OpenRouter API key. Then:

```bash
uv sync
echo "OPENROUTER_API_KEY=your_key_here" > .env
uv run python app.py
```

Once it's up, open http://localhost:5050.

The knowledge graph is cached in `data/legal_kg.ttl` and is not invalidated automatically, so rerun `uv run python -m scripts.kg_builder` after changing `scripts/kg_builder.py` or the CSV. The Canadian and New Zealand corpora are published in their national XML formats rather than AKN; `uv run python scripts/04_convert_national_xml_to_akn.py` regenerates the AKN versions the pipeline reads.

## What it's built on

The web app is Flask. The knowledge graph is handled with rdflib (RDF/Turtle, queried with SPARQL), the legal texts are stored as Akoma Ntoso XML, and the domain vocabulary comes from the IPROnto ontology. XML parsing is done with lxml and we use Pydantic v2 for schema validation. The LLM is accessed through OpenRouter; `scripts/llm_agent.py` tries a list of models in order, defaulting to free-tier Gemma 4 with Gemini 2.5 Flash as a paid fallback, and drops to a deterministic implementation if none answers.

## Paper

The full write-up, with the architecture details and a discussion of limitations and future work, is in [`paper/ReMeP_Hackathon_IP_Law_knitted.pdf`](paper/ReMeP_Hackathon_IP_Law_knitted.pdf). The LaTeX source lives in [`paper/main.tex`](paper/main.tex).
