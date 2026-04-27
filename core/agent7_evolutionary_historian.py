import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv(r'C:\foundry_project\.env')
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

STATE_PATH = r'C:\foundry_project\dashboard\OSINT_System_State\osint_state.json'
INTAKE_LOG = r'C:\foundry_project\dashboard\OSINT_System_State\scored_intake_log.json'
WINNING_URLS = r'C:\foundry_project\dashboard\winning_urls.json'
# Assuming your seed list is here:
SEED_LIST_PATH = r'C:\foundry_project\dashboard\morning_intake.json' 

def optimize_pipeline():
    print("[AGENT 7] Archiving & Evolving Seed List...")
    
    with open(INTAKE_LOG, 'r') as f: intake = json.load(f)
    with open(WINNING_URLS, 'r') as f: winners = json.load(f)
    with open(SEED_LIST_PATH, 'r') as f: seeds = json.load(f)

    # 1. Update Global State (History)
    with open(STATE_PATH, 'r') as f: state = json.load(f)
    for w in winners:
        if w['link'] not in state['processed_urls']:
            state['processed_urls'].append(w['link'])
    # In a real cloud setup, you'd upload state to your 15TB cloud here.
    with open(STATE_PATH, 'w') as f: json.dump(state, f, indent=4)

    # 2. Cull the Seeds
    # Logic: Identify feeds that produced 0 articles scoring > 70 today.
    high_performers = {item['source_feed'] for item in intake if item['score'] > 70}
    original_count = len(seeds)
    # Only keep seeds that provided value OR are protected essential feeds
    seeds = [s for s in seeds if s['url'] in high_performers or s.get('protected', False)]
    print(f"  -> Culled {original_count - len(seeds)} low-performing seed sources.")

    # 3. Hunt for New Seeds
    # Analyze the top winning URL content to find related RSS/Domains
    new_discovery = []
    for winner in winners[:3]: # Only use top 3 to save tokens
        prompt = f"Based on this high-value article link: {winner['link']}, suggest 2 similar RSS feed URLs or niche news domains for B2B intelligence in Milwaukee or AI tech. Return ONLY a JSON list of strings."
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        try:
            suggested = json.loads(response.text.strip())
            for url in suggested:
                if url not in [s['url'] for s in seeds]:
                    new_discovery.append({"url": url, "topic": "DISCOVERED"})
        except: continue

    seeds.extend(new_discovery)
    with open(SEED_LIST_PATH, 'w') as f: json.dump(seeds, f, indent=4)
    print(f"  -> Discovered and added {len(new_discovery)} new potential sources.")

if __name__ == "__main__":
    optimize_pipeline()