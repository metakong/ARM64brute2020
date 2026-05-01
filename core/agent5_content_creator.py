import os
from pathlib import Path
import json
import time
import random
from pydantic import BaseModel
from typing import Literal
from google import genai
from google.genai import types
from dotenv import load_dotenv

from dsie_utils import log_action, execute_with_backoff, clean_json_response, GEMINI_MODEL

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(str(BASE_DIR / 'secrets' / '.env'))
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
client = genai.Client(api_key=GOOGLE_API_KEY)

CONSOLIDATED_BRIEFS_PATH = str(BASE_DIR / 'dashboard' / 'consolidated_briefs.json')
AGENT_5_OUTPUT_PATH = str(BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'agent5_content_staging.json')
LOG_FILE = str(BASE_DIR / 'logs' / 'agent5_content_log.txt')

os.makedirs(os.path.dirname(AGENT_5_OUTPUT_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

class ArticleContent(BaseModel):
    pillar: Literal[
        "CLIENT PROSPECTING & COMPETITIVE INTELLIGENCE",
        "TECHNICAL TOOLING & STACK MAINTENANCE",
        "STRATEGIC BUSINESS & TECHNICAL EDUCATION",
        "SPORTS & RECREATIONAL AWARENESS"
    ]
    ui_headline: str
    ui_single_sentence_summary: str
    longform_markdown_article_text: str

def create_longform_content(brief):
    prompt = f"""
    You are a professional, highly objective B2B Technology and Local Business Journalist.

    You are provided with a 'cluster_topic', an 'executive_summary', 'key_details', and 'source_links'.
    Your task is to transform this bulleted intelligence into a cohesive, longform news article and categorize it into ONE of four strict pillars.

    ### RAW INTELLIGENCE TO USE:
    {json.dumps(brief, indent=2)}

    ### TASK 1: CATEGORIZATION
    You MUST categorize this article into exactly ONE of the following four pillars based on these definitions:

    1. "CLIENT PROSPECTING & COMPETITIVE INTELLIGENCE"
    - PURPOSE: Identify potential B2B prospects or leads or market shifts or competitor intelligence news happening within a 60 mile radius of Milwaukee, Wisconsin.
    - DIRECTIVE: Prioritize news regarding Milwaukee-area business expansions, commercial transactions, executive leadership changes, business decision maker complaints about workflow automation isses or direct requests for AI automation solutions, or municipal development projects.

    2. "TECHNICAL TOOLING & STACK MAINTENANCE"
    - PURPOSE: Maintain the integrity and capability of the user's specific technology stack.
    - USER TECH STACK: Python, LLMs, SLMs, AI models, Vector Databases (Chroma, Pinecone, Milvus), Google Drive/Cloud APIs, Web/Browser Automation frameworks, langgraph, crewai, MCP, and any potentially useful or related tools or architecture.
    - DIRECTIVE: Prioritize release notes, API deprecation warnings, technical breakthroughs, or important news within the AI industry or broader tech landscape.

    3. "STRATEGIC BUSINESS & TECHNICAL EDUCATION"
    - PURPOSE: Enhance the user's long-term capability in B2B sales, AI implementation strategy, and solopreneurship.
    - DIRECTIVE: Identify high-objectivity reports regarding enterprise AI adoption trends, automation augmented by AI, scalable business workflows, and related topics. Exclude subjective opinion pieces or hype based marketing materials.

    4. "SPORTS & RECREATIONAL AWARENESS"
    - PURPOSE: Provide a brief awareness of major professional sports news for entertainment purposes.
    - DIRECTIVE: Select only sports headlines related to the Buffalo Bills, Green Bay Packers, New York Knicks, Milwaukee Bucks, Milwaukee Brewers, Atlanta Braves, Buffalo Sabres, Minnesota Wild, and major general sports breaking news.

    ### TASK 2: WRITING THE ARTICLE
    - Write a cohesive, flowing news article. DO NOT write a listicle or use bullet points for the main body. 
    - You ABSOLUTELY MUST consider and incorporate the facts from the 'executive_summary' and 'key_details'.
    - Write objectively. Remove all marketing hype.
    - Append the 'source_links' as a bulleted 'Sources:' list at the very bottom of the article.

    ### TASK 3: UI ELEMENTS
    - Create a 3 to 5 word "ui_headline".
    - Create a single-sentence "ui_single_sentence_summary".
    """
    
    def _generate():
        # UPDATED: Current 2026 model for speed and large context windows
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ArticleContent,
                temperature=0.2
            )
        )
        safe_text = clean_json_response(response.text)
        return json.loads(safe_text)
        
    return execute_with_backoff(_generate)

def run_content_creator():
    log_action("\n==================================================", LOG_FILE)
    log_action("[AGENT 5] Booting Content Creator & Categorizer...", LOG_FILE)
    
    if not os.path.exists(CONSOLIDATED_BRIEFS_PATH):
        log_action("[FATAL] Consolidated briefs not found.", LOG_FILE)
        return
        
    with open(CONSOLIDATED_BRIEFS_PATH, 'r', encoding='utf-8') as f:
        briefs = json.load(f)
        
    if not briefs:
        log_action("[ERROR] No briefs available to process.", LOG_FILE)
        return

    # 1. RESUME CHECK: State Tracking
    final_payload = []
    processed_topics = set()
    
    if os.path.exists(AGENT_5_OUTPUT_PATH):
        try:
            with open(AGENT_5_OUTPUT_PATH, 'r', encoding='utf-8') as f:
                final_payload = json.load(f)
                processed_topics = {article.get('Original Topic') for article in final_payload if article.get('Original Topic')}
                log_action(f"[SYSTEM] Found existing progress. Loaded {len(processed_topics)} completed articles.", LOG_FILE)
        except:
            log_action("[SYSTEM] Staging file corrupted or empty. Starting fresh.", LOG_FILE)
            final_payload = []

    log_action(f"[SYSTEM] Total intelligence briefs pending generation: {len(briefs)}.", LOG_FILE)
    
    for idx, brief in enumerate(briefs):
        topic_name = brief.get('cluster_topic', 'Unknown Topic')
        
        # 2. SKIP IF ALREADY PROCESSED
        if topic_name in processed_topics:
            continue
            
        log_action(f"  -> Writing Article [{idx+1}/{len(briefs)}]: {topic_name[:40]}...", LOG_FILE)
        
        article_data = create_longform_content(brief)
        
        if article_data:
            formatted_data = {
                "Original Topic": topic_name, # Added tracking key for resume logic
                "Pillar": article_data["pillar"],
                "UI Headline": article_data["ui_headline"],
                "UI Single-Sentence Summary": article_data["ui_single_sentence_summary"],
                "Longform Markdown Article Text": article_data["longform_markdown_article_text"]
            }
            final_payload.append(formatted_data)
            
            # 3. INCREMENTAL SAVE: Protect the 90-minute marathon
            with open(AGENT_5_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                json.dump(final_payload, f, indent=4)
        else:
            log_action(f"     [SKIPPED] Critical failure generating article for: {topic_name[:40]}", LOG_FILE)
        
        time.sleep(2)

    log_action(f"\n[SUCCESS] Agent 5 complete. Finalized {len(final_payload)} longform articles.", LOG_FILE)

if __name__ == "__main__":
    run_content_creator()