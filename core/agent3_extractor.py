import os
from pathlib import Path
import json
import time
import random
import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

from dsie_utils import log_action, execute_with_backoff, clean_json_response, GEMINI_MODEL

# --- CONFIGURATION ---
load_dotenv(str(BASE_DIR / '.env'))
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
client = genai.Client(api_key=GOOGLE_API_KEY)

WINNING_URLS_PATH = str(BASE_DIR / 'dashboard' / 'winning_urls.json')
ATOMIC_FACTS_PATH = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'atomic_facts_log.json')
LOG_FILE = str(BASE_DIR / 'logs' / 'agent3_extractor_log.txt')

os.makedirs(os.path.dirname(ATOMIC_FACTS_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def fetch_markdown_with_jina(target_url):
    jina_url = f"https://r.jina.ai/{target_url}"
    headers = {
        "Accept": "text/event-stream",
        "X-Return-Format": "markdown"
    }
    
    def _fetch():
        response = requests.get(jina_url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.text
        
    return execute_with_backoff(_fetch)

def extract_atomic_facts(markdown_content):
    prompt = f"""
    ### ROLE
    You are an Elite Intelligence Extractor. Your job is to process raw markdown extracted from web pages and isolate the "Atomic Facts."

    ### DEFINITION OF AN ATOMIC FACT
    An atomic fact is a single, verifiable piece of data stripped of all narrative, marketing spin, emotional language, and journalistic fluff. 
    - BAD: "The incredibly innovative tech giant Amazon is thrilled to announce a massive, game-changing facility in the beautiful Menomonee Valley."
    - GOOD: "Amazon is planning to build a new facility in the Menomonee Valley."

    ### TASK
    Extract all relevant business, technical, or geographic atomic facts from the provided text.

    ### OUTPUT DIRECTIVE
    Return ONLY a raw JSON array of strings. Do not include markdown formatting or backticks. If the text contains no useful facts or is an error page, return an empty array [].
    
    Format exactly like this example:
    [
      "Company X raised $5M in Series A funding on April 26, 2026.",
      "The new facility will be located at 123 Main St, Milwaukee, WI.",
      "Python 3.15.0a8 deprecates the legacy XML parser."
    ]

    ### RAW MARKDOWN CONTENT:
    {markdown_content[:25000]}
    """
    
    def _generate():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        
        return json.loads(clean_json_response(response.text))
        
    return execute_with_backoff(_generate)

def run_extractor_agent():
    log_action("\n" + "="*50, LOG_FILE)
    log_action("[AGENT 3] Booting The Extractor (Fail-Fast & Save-As-You-Go Enabled)...", LOG_FILE)
    
    if not os.path.exists(WINNING_URLS_PATH):
        log_action("[FATAL] Winning URLs queue not found.", LOG_FILE)
        return
        
    with open(WINNING_URLS_PATH, 'r', encoding='utf-8') as f:
        winning_articles = json.load(f)

    extracted_database = []
    seen_links = set()
    
    if os.path.exists(ATOMIC_FACTS_PATH):
        try:
            with open(ATOMIC_FACTS_PATH, 'r', encoding='utf-8') as f:
                extracted_database = json.load(f)
                seen_links = {item['original_link'] for item in extracted_database}
            log_action(f"[SYSTEM] Resuming. Found {len(extracted_database)} previously extracted articles.", LOG_FILE)
        except Exception as e:
            log_action(f"[WARNING] Could not load previous state: {e}", LOG_FILE)

    log_action("[SYSTEM] Commencing Extraction for remaining targets...", LOG_FILE)
    
    for idx, article in enumerate(winning_articles):
        if article['link'] in seen_links:
            continue
            
        log_action(f"  -> Processing [{idx+1}/{len(winning_articles)}]: {article['title'][:50]}...", LOG_FILE)
        
        raw_markdown = fetch_markdown_with_jina(article['link'])
        
        if not raw_markdown or len(raw_markdown) < 50:
            log_action("     [SKIP] Failed to fetch or page is empty.", LOG_FILE)
            continue
            
        facts = extract_atomic_facts(raw_markdown)
        
        if facts:
            log_action(f"     [SUCCESS] Extracted {len(facts)} atomic facts.", LOG_FILE)
            extracted_database.append({
                "original_title": article['title'],
                "original_link": article['link'],
                "source_feed": article['source_feed'],
                "original_score": article['score'],
                "atomic_facts": facts
            })
            # SAVE AS YOU GO
            with open(ATOMIC_FACTS_PATH, 'w', encoding='utf-8') as f:
                json.dump(extracted_database, f, indent=4)
        else:
            log_action("     [SKIP] No verifiable facts found in text.", LOG_FILE)
            
        time.sleep(4)

    log_action("\n[SUCCESS] Agent 3 complete.", LOG_FILE)
    log_action(f"[SYSTEM] Handoff ready at: {ATOMIC_FACTS_PATH}", LOG_FILE)

if __name__ == "__main__":
    run_extractor_agent()