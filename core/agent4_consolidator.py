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

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(str(BASE_DIR / '.env'))
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

def log_action(message):
    print(message)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")

def execute_with_backoff(func, *args, max_retries=5, **kwargs):
    base_delay = 5
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                log_action(f"     [FATAL] Max retries reached: {e}")
                raise e
            jitter = random.uniform(0, 1)
            delay = (base_delay * (2 ** attempt)) + jitter
            log_action(f"     [API THROTTLE] Waiting {delay:.2f}s... ({str(e)[:40]})")
            time.sleep(delay)

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

def clean_json_response(raw_text):
    """Robustly strips markdown and trailing garbage from LLM JSON responses."""
    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        lines = clean_text.split('\n')
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean_text = '\n'.join(lines).strip()
    return clean_text

def categorize_batch(articles_batch):
    prompt = f"""
    Categorize each of the following articles into a broad "Topic Tag".
    Use exact matching Topic Tags for related items.
    
    {json.dumps(articles_batch)}
    """
    def _generate():
        response = client.models.generate_content(
            model='gemini-2.5-flash',
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
            model='gemini-2.5-flash',
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
    log_action("\n==================================================")
    log_action("[AGENT 4] Booting The Consolidator...")
    
    if not os.path.exists(ATOMIC_FACTS_PATH):
        return
        
    with open(ATOMIC_FACTS_PATH, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        
    if not raw_data:
        return

    log_action("[SYSTEM] Executing programmatic boilerplate purge...")
    cleaned_data = frequency_based_purge(raw_data)
    log_action(f"[SYSTEM] Survived Purge: {len(cleaned_data)} articles with valid delta facts.")
    
    topic_groups = {}
    batch_size = 25  # Reduced from 50 to prevent JSON truncation
    
    total_batches = (len(cleaned_data) + batch_size - 1) // batch_size
    
    log_action(f"[SYSTEM] Mapping Phase: Processing {total_batches} batches...")
    for i in range(0, len(cleaned_data), batch_size):
        batch_num = (i // batch_size) + 1
        log_action(f"  -> Mapping batch {batch_num}/{total_batches}...")
        
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
        time.sleep(4)

    log_action(f"[SYSTEM] Synthesis Phase: Synthesizing {len(topic_groups)} unique topics...")
    final_briefs = []
    
    for idx, (topic, articles) in enumerate(topic_groups.items()):
        log_action(f"  -> Synthesizing [{idx+1}/{len(topic_groups)}]: {topic[:40]}...")
        brief = synthesize_topic(topic, articles)
        if brief:
            final_briefs.append(brief)
        time.sleep(4)

    with open(CONSOLIDATED_BRIEFS_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_briefs, f, indent=4)
        
    log_action(f"\n[SUCCESS] Agent 4 complete. Generated {len(final_briefs)} Briefs.")

if __name__ == "__main__":
    run_consolidator_agent()