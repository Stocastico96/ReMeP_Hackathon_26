import xml.etree.ElementTree as ET
import torch
from rdflib import Graph, Literal, RDF, URIRef, Namespace
from transformers import AutoModelForQuestionAnswering, AutoTokenizer

# 1. Setup - ML and IPROnto Namespaces
model_name = "deepset/xlm-roberta-base-squad2"
tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
model = AutoModelForQuestionAnswering.from_pretrained(model_name)

IPRONTO = Namespace("http://rhizomik.net/ontologies/2005/03/ipronto.owl#")
EX = Namespace("http://legal-kg.org/data/")

def ask_ipronto_qa(question, context):
    """Directly extracts answer snippets from legal text."""
    inputs = tokenizer(question, context, return_tensors="pt", truncation=True)
    with torch.no_grad():
        outputs = model(**inputs)
    start_idx, end_idx = torch.argmax(outputs.start_logits), torch.argmax(outputs.end_logits)
    if start_idx == 0 or start_idx > end_idx: return ""
    return tokenizer.decode(inputs.input_ids[0][start_idx:end_idx+1], skip_special_tokens=True).strip()

def build_ipronto_kg(file_path, jurisdiction):
    g = Graph()
    g.bind("ipronto", IPRONTO)
    
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return g

    # Target high-level structural containers to capture IDs correctly
    target_tags = ['article', 'paragraph', 'section', 'Section', 'prov']
    
    print(f"--- Extracting IPROnto Knowledge: {jurisdiction} ---")
    for elem in root.iter():
        tag_name = elem.tag.split('}')[-1]
        if tag_name in target_tags:
            content_text = "".join(elem.itertext()).strip()
            if len(content_text) < 50: continue

            # IPROnto Extraction Logic
            # We look for the 'Work' being protected and its 'Duration'
            work_type = ask_ipronto_qa("What type of work (e.g. musical, literary) is this protection for?", content_text)
            duration = ask_ipronto_qa("What is the exact number of years of protection?", content_text)
            
            if duration or work_type:
                # Get the unique identifier for the provision
                block_id = elem.attrib.get('eId') or elem.attrib.get('{http://justice.gc.ca/lims}id') or "node"
                subject_uri = EX[f"{jurisdiction}_{block_id}"]
                
                # Semantic Mapping to IPROnto
                g.add((subject_uri, RDF.type, IPRONTO.ExploitationRight))
                g.add((subject_uri, IPRONTO.isApplicableIn, Literal(jurisdiction)))
                
                if work_type:
                    g.add((subject_uri, IPRONTO.refersToWork, Literal(work_type)))
                
                if duration:
                    # Map the duration literal to a TemporalConstraint
                    g.add((subject_uri, IPRONTO.hasTemporalConstraint, Literal(duration)))
                    
                    # Extract the Triggering Event (Critical for IPROnto logic)
                    trigger = ask_ipronto_qa("What event (e.g. death, publication) triggers the start of the duration?", content_text)
                    if trigger:
                        g.add((subject_uri, IPRONTO.triggeredBy, Literal(trigger)))

                # Extract Economic Rights (Recognized Rights)
                rights_answer = ask_ipronto_qa("What exclusive or economic rights (e.g. reproduction, perform) are mentioned?", content_text)
                if rights_answer:
                    g.add((subject_uri, IPRONTO.recognizesRight, Literal(rights_answer)))

    return g

# Example: Building the graph across jurisdictions
if __name__ == "__main__":
    final_kg = Graph()
    # List of files and their mapped jurisdiction codes
    jurisdiction_map = {
        "cpi_copyright_act.xml": "FR",
        "C-42.xml": "CA",
        "title17_copyright_act.xml": "US",
        "19410716_041U0633_VIGENZA_20251218.xml": "IT"
    }
    
    for file, code in jurisdiction_map.items():
        final_kg += build_ipronto_kg(file, code)
        
    final_kg.serialize(destination="ipronto_legal_kg.ttl", format="turtle")
    print("IPROnto Knowledge Graph saved to ipronto_legal_kg.ttl")