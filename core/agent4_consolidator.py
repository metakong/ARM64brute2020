import os
from pathlib import Path
import json
import time
import random
import string
from collections import Counter
from pydantic import BaseModel
from typing import List
from google import genai
from google.genai import types
from dotenv import load_dotenv

from dsie_utils import log_action, execute_with_backoff, clean_json_response, GEMINI_MODEL

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(str(BASE_DIR / 'secrets' / '.env'))
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
client = genai.Client(api_key=GOOGLE_API_KEY)

ATOMIC_FACTS_PATH = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'atomic_facts_log.json')
CONSOLIDATED_BRIEFS_PATH = str(BASE_DIR / 'dashboard' / 'consolidated_briefs.json')
LOG_FILE = str(BASE_DIR / 'logs' / 'agent4_consolidator_log.txt')

os.makedirs(os.path.dirname(CONSOLIDATED_BRIEFS_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

class TopicMapping(BaseModel):
    original_link: str
    topic_tag: str

class MapperResponse(BaseModel):
    mappings: List[TopicMapping]

class ExecutiveBrief(BaseModel):
    cluster_topic: str
    executive_summary: str
    key_details: List[str]
    source_links: List[str]

def normalize_fact(fact):
    return fact.strip().lower().translate(str.maketrans('', '', string.punctuation))

def frequency_based_purge(raw_data):
    fact_counts = Counter()
    for article in raw_data:
        for fact in article.get('atomic_facts', []):
            fact_counts[normalize_fact(fact)] += 1

    cleaned_articles = []
    for article in raw_data:
        clean_facts = []
        for fact in article.get('atomic_facts', []):
            if fact_counts[normalize_fact(fact)] < 4:
                clean_facts.append(fact)
        if clean_facts:
            cleaned_articles.append({
                "title": article['original_title'],
                "link": article['original_link'],
                "score": article['original_score'],
                "facts": clean_facts
            })
    return cleaned_articles

def categorize_batch(articles_batch):
    prompt = f"""
    Categorize each of the following articles into a broad "Topic Tag".
    Use exact matching Topic Tags for related items.
    
    {json.dumps(articles_batch)}
    """
    def _generate():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MapperResponse,
                temperature=0.1
            )
        )
        safe_text = clean_json_response(response.text)
        return json.loads(safe_text)
    return execute_with_backoff(_generate)

def synthesize_topic(topic, articles):
    prompt = f"""
    Topic: {topic}
    Write an objective Executive Brief summarizing the following facts.
    
    {json.dumps(articles)}
    """
    def _generate():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExecutiveBrief,
                temperature=0.1
            )
        )
        safe_text = clean_json_response(response.text)
        return json.loads(safe_text)
    return execute_with_backoff(_generate)

def run_consolidator_agent():
    log_action("\n==================================================", LOG_FILE)
    log_action("[AGENT 4] Booting The Consolidator...", LOG_FILE)
    
    if not os.path.exists(ATOMIC_FACTS_PATH):
        log_action("[ERROR] Atomic facts log not found. Aborting.", LOG_FILE)
        return
        
    with open(ATOMIC_FACTS_PATH, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        
    if not raw_data:
        log_action("[ERROR] Atomic facts log is empty. Aborting.", LOG_FILE)
        return

    final_briefs = []
    processed_topics = set()
    if os.path.exists(CONSOLIDATED_BRIEFS_PATH):
        try:
            with open(CONSOLIDATED_BRIEFS_PATH, 'r', encoding='utf-8') as f:
                final_briefs = json.load(f)
                processed_topics = {b['cluster_topic'] for b in final_briefs}
                log_action(f"[SYSTEM] Found existing progress. Loaded {len(processed_topics)} briefs.", LOG_FILE)
        except:
            log_action("[SYSTEM] Existing briefs file corrupted or empty. Starting fresh.", LOG_FILE)
            final_briefs = []

    log_action("[SYSTEM] Executing programmatic boilerplate purge...", LOG_FILE)
    cleaned_data = frequency_based_purge(raw_data)
    log_action(f"[SYSTEM] Survived Purge: {len(cleaned_data)} articles with valid delta facts.", LOG_FILE)
    
    topic_groups = {}
    batch_size = 25  
    
    total_batches = (len(cleaned_data) + batch_size - 1) // batch_size
    
    log_action(f"[SYSTEM] Mapping Phase: Processing {total_batches} batches...", LOG_FILE)
    for i in range(0, len(cleaned_data), batch_size):
        batch_num = (i // batch_size) + 1
        log_action(f"  -> Mapping batch {batch_num}/{total_batches}...", LOG_FILE)
        
        batch = cleaned_data[i:i + batch_size]
        payload = [{"link": a['link'], "title": a['title']} for a in batch]
        mapping_result = categorize_batch(payload)
        
        if mapping_result and 'mappings' in mapping_result:
            for mapping in mapping_result['mappings']:
                tag = mapping['topic_tag']
                link = mapping['original_link']
                article = next((a for a in batch if a['link'] == link), None)
                if article:
                    if tag not in topic_groups:
                        topic_groups[tag] = []
                    topic_groups[tag].append(article)
        time.sleep(2)

    log_action(f"[SYSTEM] Synthesis Phase: Synthesizing {len(topic_groups)} unique topics...", LOG_FILE)
    
    for idx, (topic, articles) in enumerate(topic_groups.items()):
        if topic in processed_topics:
            continue

        log_action(f"  -> Synthesizing [{idx+1}/{len(topic_groups)}]: {topic[:40]}...", LOG_FILE)
        
        brief = synthesize_topic(topic, articles)
        
        if brief:
            final_briefs.append(brief)
            with open(CONSOLIDATED_BRIEFS_PATH, 'w', encoding='utf-8') as f:
                json.dump(final_briefs, f, indent=4)
        else:
            log_action(f"     [SKIPPED] Critical failure on Topic: {topic[:40]}. Moving to next.", LOG_FILE)
            
        time.sleep(2)

    log_action(f"\n[SUCCESS] Agent 4 complete. Finalized {len(final_briefs)} Briefs.", LOG_FILE)

if __name__ == "__main__":
    run_consolidator_agent()