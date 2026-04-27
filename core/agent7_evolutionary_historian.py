import os
import json
import re
import time
import random
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(str(BASE_DIR / '.env'))
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

STATE_PATH = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'osint_state.json')
INTAKE_LOG = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'scored_intake_log.json')
WINNING_URLS = str(BASE_DIR / 'dashboard' / 'winning_urls.json')
SEED_LIST_PATH = str(BASE_DIR / 'OSINT Seed List Generation.md')
LOG_FILE = str(BASE_DIR / 'logs' / 'agent7_historian_log.txt')

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log_action(message):
    print(message)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")

def execute_with_backoff(func, *args, max_retries=4, **kwargs):
    base_delay = 5
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries - 1:
                log_action(f"     [FATAL] Max retries reached: {e}")
                return None
            jitter = random.uniform(0, 1)
            delay = (base_delay * (2 ** attempt)) + jitter
            log_action(f"     [API THROTTLE] Waiting {delay:.2f}s... ({str(e)[:40]})")
            time.sleep(delay)

def extract_existing_urls_from_markdown(md_path):
    """Extracts all URLs already present in the Markdown seed list to prevent duplicates."""
    urls = set()
    if not os.path.exists(md_path):
        return urls
    with open(md_path, 'r', encoding='utf-8') as f:
        for line in f:
            match = re.search(r'(https?://[^\s\|\)]+)', line)
            if match:
                urls.add(match.group(1).strip())
    return urls

def optimize_pipeline():
    log_action("\n" + "="*50)
    log_action("[AGENT 7] Booting Evolutionary Historian...")

    # --- 1. Update Global State (History) ---
    if not os.path.exists(WINNING_URLS):
        log_action("[FATAL] Winning URLs not found. Aborting.")
        return

    with open(WINNING_URLS, 'r', encoding='utf-8') as f:
        winners = json.load(f)

    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, 'r', encoding='utf-8') as f:
            try:
                state = json.load(f)
            except json.JSONDecodeError:
                state = {"processed_urls": []}
    else:
        state = {"processed_urls": []}

    new_urls_archived = 0
    for w in winners:
        if w['link'] not in state['processed_urls']:
            state['processed_urls'].append(w['link'])
            new_urls_archived += 1

    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=4)

    log_action(f"  -> Archived {new_urls_archived} new winning URLs to global state.")

    # --- 2. Cull Low-Performers from Scored Intake ---
    if os.path.exists(INTAKE_LOG):
        with open(INTAKE_LOG, 'r', encoding='utf-8') as f:
            intake = json.load(f)
        high_performers = {item['source_feed'] for item in intake if item.get('score', 0) > 70}
        log_action(f"  -> High-performing source feeds today: {len(high_performers)}")
    else:
        high_performers = set()
        log_action("  -> [WARNING] No scored intake log found. Skipping cull analysis.")

    # --- 3. Hunt for New Seeds via LLM & Append to Markdown ---
    existing_urls = extract_existing_urls_from_markdown(SEED_LIST_PATH)
    log_action(f"  -> Current seed list contains {len(existing_urls)} unique URLs.")

    new_discoveries = []

    for winner in winners[:3]:  # Only use top 3 to save tokens
        log_action(f"  -> Discovering new feeds based on: {winner.get('title', 'N/A')[:50]}...")

        prompt = f"""Based on this high-value intelligence article:
Title: {winner.get('title', 'N/A')}
Link: {winner['link']}

Suggest 2-3 new RSS feed URLs or JSON API endpoints that would provide similar high-value intelligence for:
- B2B business intelligence in the Milwaukee, Wisconsin metro area
- AI/ML technical tooling and industry news
- Open source intelligence gathering

Return ONLY a raw JSON array of objects with "url" and "topic" keys. Example:
[{{"url": "https://example.com/feed.xml", "topic": "Milwaukee Business News"}}]
"""

        def _generate():
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            clean_text = response.text.strip()
            if clean_text.startswith("```"):
                lines = clean_text.split('\n')
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean_text = '\n'.join(lines).strip()
            return json.loads(clean_text)

        result = execute_with_backoff(_generate)

        if result and isinstance(result, list):
            for entry in result:
                url = entry.get('url', '')
                topic = entry.get('topic', 'DISCOVERED')
                if url and url.startswith('http') and url not in existing_urls:
                    new_discoveries.append({"url": url, "topic": topic})
                    existing_urls.add(url)

        time.sleep(4)

    # --- 4. Append Discoveries as Markdown Table Rows ---
    if new_discoveries:
        log_action(f"  -> Appending {len(new_discoveries)} new seed URLs to master seed list...")
        with open(SEED_LIST_PATH, 'a', encoding='utf-8') as f:
            f.write("\n\n<!-- === AGENT 7 AUTO-DISCOVERED FEEDS === -->\n")
            f.write(f"<!-- Discovery Date: {time.strftime('%Y-%m-%d %H:%M:%S')} -->\n")
            f.write("| Source Name | URL | Topic | Status |\n")
            f.write("|---|---|---|---|\n")
            for entry in new_discoveries:
                safe_url = entry['url'].replace('|', '%7C')
                safe_topic = entry['topic'].replace('|', '-')
                f.write(f"| Auto-Discovered | [{safe_url}]({safe_url}) | {safe_topic} | NEW |\n")
                log_action(f"     [NEW SEED] {entry['url'][:60]}")
    else:
        log_action("  -> No new unique feeds discovered this cycle.")

    log_action("\n[SUCCESS] Agent 7 complete. Seed list evolution cycle finished.")

if __name__ == "__main__":
    optimize_pipeline()