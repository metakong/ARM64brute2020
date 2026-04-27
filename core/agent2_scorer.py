import os
from pathlib import Path
import json
import time
import random
from google import genai
from google.genai import types
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# --- CONFIGURATION ---
load_dotenv(str(BASE_DIR / '.env'))
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
client = genai.Client(api_key=GOOGLE_API_KEY)

INTAKE_QUEUE_PATH = str(BASE_DIR / 'dashboard' / 'morning_intake.json')
WINNING_URLS_PATH = str(BASE_DIR / 'dashboard' / 'winning_urls.json')
SCORED_LOG_PATH = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'scored_intake_log.json')
LOG_FILE = str(BASE_DIR / 'logs' / 'agent2_scorer_log.txt')

SCORE_THRESHOLD = 80
BATCH_SIZE = 20  # Batching to avoid Gemini 15 RPM Free Tier limits

os.makedirs(os.path.dirname(SCORED_LOG_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log_action(message):
    print(message)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")

def execute_with_backoff(func, *args, max_retries=5, **kwargs):
    """Exponential backoff for API rate limits."""
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
            log_action(f"     [API THROTTLE/ERROR] Waiting {delay:.2f}s... ({str(e)[:50]})")
            time.sleep(delay)

def score_batch_with_gemini(article_batch):
    """Sends a batch of 20 articles to Gemini to be scored simultaneously."""
    
    payload = []
    for idx, article in enumerate(article_batch):
        payload.append({
            "id": idx,
            "title": article['title'],
            "snippet": article['summary_snippet'],
            "source_feed": article['source_feed']
        })
        
    prompt = f"""
### ROLE
You are a Chief Intelligence Officer for a solo AI-system integration consultancy. Your task is to provide high-precision filtering of morning news to identify revenue opportunities, technical necessities, and relevant education.

### TASK
Analyze the provided batch of {len(article_batch)} articles. Assign each article an alignment score from 0 to 100 based on the following four pillars of business value.

### PILLAR 1: CLIENT PROSPECTING & COMPETITIVE INTELLIGENCE
- PURPOSE: Identify potential B2B prospects or leads or market shifts or competitor intelligence news happening within a 60 mile radius of Milwaukee, Wisconsin.
- DIRECTIVE: Prioritize news regarding Milwaukee-area business expansions, commercial transactions, executive leadership changes, business decision maker complaints about workflow automation isses or direct requests for AI automation solutions, or municipal development projects.
- PROXIMITY RULE: Apply a score increase for geographic proximity ONLY within this pillar. Articles concerning business leads outside of the Midwest must be scored below 50 unless they represent a direct competitive threat to the user's local Milwaukee market.

### PILLAR 2: TECHNICAL TOOLING & STACK MAINTENANCE
- PURPOSE: Maintain the integrity and capability of the user's specific technology stack.
- USER TECH STACK: Python, LLMs, SLMs, AI models, Vector Databases (Chroma, Pinecone, Milvus), Google Drive/Cloud APIs, Web/Browser Automation frameworks, langgraph, crewai, MCP, and any potentially useful or related tools or architecture.
- DIRECTIVE: Prioritize release notes, API deprecation warnings, technical breakthroughs, or important news within the AI industry or broader tech landscape. Location is irrelevant for this pillar; prioritize technical impact and recency.

### PILLAR 3: STRATEGIC BUSINESS & TECHNICAL EDUCATION
- PURPOSE: Enhance the user's long-term capability in B2B sales, AI implementation strategy, and solopreneurship.
- DIRECTIVE: Identify high-objectivity reports regarding enterprise AI adoption trends, automation augmented by AI, scalable business workflows, and related topics that can increase understanding of the overarching and related tech landscape. Exclude subjective opinion pieces or hype based marketing materials.

### PILLAR 4: SPORTS & RECREATIONAL AWARENESS
- PURPOSE: Provide a brief awareness of major professional sports news for entertainment purposes.
- DIRECTIVE: Select only the sports headlines related to the Buffalo Bills, Green Bay Packers, New York Knicks, Milwaukee Bucks, Milwaukee Brewers, Atlanta Braves, Buffalo Sabres, Minnesota Wild, and more general sports headlines that seem to be highly popular or important breaking news items related to well-known sports figures or athletes.  Entertainment for the sake of psychological well-being and breaks from the daily workflow is just as valuable as any other pillar.

### SCORING RUBRIC
- 80-100 (HIGH ALIGNMENT): Direct Milwaukee business leads/prospective leads/competitor analysis/news/updates, newer information related to all related technical or business concepts that will provide high value for continuing education, and critical utility or security updates to anything related to the business tech stack.
- 60-79 (MODERATE ALIGNMENT): Anything that is seemingly related to the above high alignment description, but does not quite qualify as high value due to the content being generally known within the related space/subject area/topic of interest; anything that is actually old news; and, anything that simply isnt that useful nor entertaining.
- 0-59 (LOW ALIGNMENT): Irrelevant geographic business updates, non-technical opinion content, hyped-based marketing material, or information that is seemingly reduntant redundant to the user's existing knowledge; an article gets a low alignment score if it is the opposite of the high alignment description above and doesn't quite come close enough to being described by the definition of moderate alignment above.

### ARTICLES TO SCORE:
{json.dumps(payload, indent=2)}

### OUTPUT DIRECTIVE
Return ONLY a raw JSON array of objects. Do not include markdown formatting or commentary. Use the following structure:
[
  {{"id": 0, "total_score": 85, "justification": "Direct Milwaukee commercial real estate lead involving a potential automation-heavy warehouse expansion."}},
  {{"id": 1, "total_score": 20, "justification": "Opinion piece regarding general AI ethics in Australia; no local or technical utility."}}
]
"""
    
    def _generate():
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        
        clean_text = response.text.strip()
        # Clean any accidental markdown formatting robustly
        if clean_text.startswith("```"):
            lines = clean_text.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_text = '\n'.join(lines).strip()
            
        return json.loads(clean_text)
        
    return execute_with_backoff(_generate)

def run_scorer_agent():
    log_action("\n" + "="*50)
    log_action(f"[AGENT 2] Booting The Scorer (Threshold: {SCORE_THRESHOLD}+)...")
    
    if not os.path.exists(INTAKE_QUEUE_PATH):
        log_action("[FATAL] Intake queue not found. Did Agent 1 run?")
        return
        
    with open(INTAKE_QUEUE_PATH, 'r', encoding='utf-8') as f:
        morning_intake = json.load(f)
        
    if not morning_intake:
        log_action("[SYSTEM] Intake queue is empty. Exiting.")
        return

    log_action(f"[SYSTEM] Loaded {len(morning_intake)} articles. Commencing Batch Scoring...")
    
    all_scored_articles = []
    winning_articles = []
    
    for i in range(0, len(morning_intake), BATCH_SIZE):
        batch = morning_intake[i:i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (len(morning_intake) - 1) // BATCH_SIZE + 1
        
        log_action(f"  -> Scoring Batch {batch_num}/{total_batches} ({len(batch)} articles)...")
        
        try:
            batch_results = score_batch_with_gemini(batch)
            
            for result in batch_results:
                idx = result.get('id')
                if idx is not None and idx < len(batch):
                    article = batch[idx]
                    score = result.get('total_score', 0)
                    
                    scored_record = {
                        "title": article['title'],
                        "link": article['link'],
                        "source_feed": article['source_feed'],
                        "score": score,
                        "justification": result.get('justification', '')
                    }
                    all_scored_articles.append(scored_record)
                    
                    if score >= SCORE_THRESHOLD:
                        log_action(f"     [WINNER: {score}/100] {article['title'][:60]}...")
                        winning_articles.append(scored_record)
            
            # Artificial delay to respect Gemini API RPM limits for Free Tier
            time.sleep(5)
            
        except Exception as e:
            log_action(f"     [ERROR] Batch {batch_num} failed: {e}")

    # Save outputs
    with open(SCORED_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_scored_articles, f, indent=4)
        
    with open(WINNING_URLS_PATH, 'w', encoding='utf-8') as f:
        json.dump(winning_articles, f, indent=4)
        
    log_action(f"\n[SUCCESS] Agent 2 complete.")
    log_action(f"  -> Processed: {len(all_scored_articles)}")
    log_action(f"  -> Winners ({SCORE_THRESHOLD}+): {len(winning_articles)}")
    log_action(f"  -> Rejected: {len(all_scored_articles) - len(winning_articles)}")
    log_action(f"[SYSTEM] Scored log: {SCORED_LOG_PATH}")
    log_action(f"[SYSTEM] Handoff ready: {WINNING_URLS_PATH}")

if __name__ == "__main__":
    run_scorer_agent()