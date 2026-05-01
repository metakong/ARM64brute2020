import os
import json
import re
import time
import random
import string
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv

from dsie_utils import log_action, execute_with_backoff, clean_json_response, GEMINI_MODEL

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(str(BASE_DIR / 'secrets' / '.env'))
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

STATE_PATH = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'osint_state.json')
INTAKE_LOG = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'scored_intake_log.json')
WINNING_URLS = str(BASE_DIR / 'dashboard' / 'winning_urls.json')
SEED_LIST_PATH = str(BASE_DIR / 'OSINT Seed List Generation.md')
LOG_FILE = str(BASE_DIR / 'logs' / 'agent7_historian_log.txt')

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

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

def detect_table_columns(md_path):
    """Read the seed list and detect the column headers from the first Markdown table found."""
    default_cols = ["Source Name", "Verified Native URL", "Data Format", "Relevance"]
    if not os.path.exists(md_path):
        return default_cols
    with open(md_path, 'r', encoding='utf-8') as f:
        for line in f:
            stripped = line.strip()
            # Find the first line that looks like a table header row (contains pipes and letters)
            if stripped.startswith('|') and not stripped.startswith('| :') and not stripped.startswith('|--'):
                # Split by pipe, strip whitespace, filter empty strings
                cols = [c.strip() for c in stripped.split('|') if c.strip()]
                if len(cols) >= 2:
                    return cols
    return default_cols

def optimize_pipeline():
    log_action("\n" + "="*50, LOG_FILE)
    log_action("[AGENT 7] Booting Evolutionary Historian...", LOG_FILE)

    # --- 1. Update Global State (History) ---
    if not os.path.exists(WINNING_URLS):
        log_action("[FATAL] Winning URLs not found. Aborting.", LOG_FILE)
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

    log_action(f"  -> Archived {new_urls_archived} new winning URLs to global state.", LOG_FILE)

    # --- 2. Cull Low-Performers from Scored Intake ---
    if os.path.exists(INTAKE_LOG):
        with open(INTAKE_LOG, 'r', encoding='utf-8') as f:
            intake = json.load(f)
        high_performers = {item['source_feed'] for item in intake if item.get('score', 0) > 70}
        log_action(f"  -> High-performing source feeds today: {len(high_performers)}", LOG_FILE)
    else:
        high_performers = set()
        log_action("  -> [WARNING] No scored intake log found. Skipping cull analysis.", LOG_FILE)

    # --- 3. Hunt for New Seeds via LLM & Append to Markdown ---
    existing_urls = extract_existing_urls_from_markdown(SEED_LIST_PATH)
    log_action(f"  -> Current seed list contains {len(existing_urls)} unique URLs.", LOG_FILE)

    new_discoveries = []

    # SAFETY CHECK: Ensure we have winners to analyze
    if not winners:
         log_action("  -> [WARNING] No winning URLs today. Skipping feed discovery.", LOG_FILE)
    else:
        for winner in winners[:3]:  # Only use top 3 to save tokens
            log_action(f"  -> Discovering new feeds based on: {winner.get('title', 'N/A')[:50]}...", LOG_FILE)

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
                # UPDATED: Standardized to the 2026 stable API endpoint
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3
                    )
                )
                # UPDATED: Using the robust JSON cleaner
                safe_text = clean_json_response(response.text)
                return json.loads(safe_text)

            result = execute_with_backoff(_generate)

            if result and isinstance(result, list):
                for entry in result:
                    url = entry.get('url', '')
                    topic = entry.get('topic', 'DISCOVERED')
                    if url and url.startswith('http') and url not in existing_urls:
                        new_discoveries.append({"url": url, "topic": topic})
                        existing_urls.add(url)

            time.sleep(4)

    # --- 4. Append Discoveries as Markdown Table Rows (Structure-Aware) ---
    if new_discoveries:
        # Detect the existing table column structure from the seed list
        columns = detect_table_columns(SEED_LIST_PATH)
        num_cols = len(columns)
        log_action(f"  -> Detected {num_cols}-column table structure: {columns}", LOG_FILE)
        log_action(f"  -> Appending {len(new_discoveries)} new seed URLs to master seed list...", LOG_FILE)

        with open(SEED_LIST_PATH, 'a', encoding='utf-8') as f:
            # Enforce leading newline to prevent corrupting the last line of existing content
            f.write("\n\n\n")
            f.write(f"\n")

            # Write a header row matching the detected column structure
            header_row = "| " + " | ".join(columns) + " |\n"
            separator_row = "| " + " | ".join([":----"] * num_cols) + " |\n"
            f.write(header_row)
            f.write(separator_row)

            for entry in new_discoveries:
                # Sanitize pipe characters in all values to prevent table corruption
                safe_url = entry['url'].replace('|', '%7C')
                safe_topic = entry['topic'].replace('|', '-')

                # Build the row to match the detected column count exactly
                if num_cols == 4:
                    # Matches: | Source Name | Verified Native URL | Data Format | Relevance |
                    data_format = "XML" if any(ext in safe_url.lower() for ext in ['.xml', '/feed', '/rss', '.atom', '.rss']) else "JSON"
                    row = f"| Auto-Discovered | [{safe_url}]({safe_url}) | {data_format} | {safe_topic} |\n"
                elif num_cols == 3:
                    row = f"| Auto-Discovered | [{safe_url}]({safe_url}) | {safe_topic} |\n"
                else:
                    # Fallback: 2-column or unknown — just use Source + URL
                    row = f"| Auto-Discovered | [{safe_url}]({safe_url}) |" + " |" * max(0, num_cols - 2) + "\n"

                f.write(row)
                log_action(f"     [NEW SEED] {entry['url'][:60]}", LOG_FILE)
    else:
        log_action("  -> No new unique feeds discovered this cycle.", LOG_FILE)

    log_action("\n[SUCCESS] Agent 7 complete. Seed list evolution cycle finished.", LOG_FILE)

if __name__ == "__main__":
    optimize_pipeline()