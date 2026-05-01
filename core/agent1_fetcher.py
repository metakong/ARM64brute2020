import os
from pathlib import Path
import json
import time
import re
import io
import feedparser
import cloudscraper
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

BASE_DIR = Path(__file__).resolve().parent.parent

from dsie_utils import log_action

# --- CONFIGURATION ---
SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_SECRET_FILE = str(BASE_DIR / 'secrets' / 'client_secret.json')
TOKEN_FILE = str(BASE_DIR / 'secrets' / 'token.json')

SEED_LIST_PATH = str(BASE_DIR / 'OSINT Seed List Generation.md')
INTAKE_QUEUE_PATH = str(BASE_DIR / 'dashboard' / 'morning_intake.json')
LOCAL_STATE_DIR = str(BASE_DIR / 'dashboard' / 'OSINT_System_State')
LOCAL_STATE_PATH = os.path.join(LOCAL_STATE_DIR, 'osint_state.json')
LOG_FILE = str(BASE_DIR / 'logs' / 'agent1_fetcher_log.txt')

# Ensure directories exist
os.makedirs(LOCAL_STATE_DIR, exist_ok=True)
os.makedirs(str(BASE_DIR / 'logs'), exist_ok=True)

# --- GOOGLE DRIVE AUTH & STATE MANAGEMENT ---
def authenticate_drive():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def get_or_create_state_folder(drive_service):
    folder_name = 'OSINT_System_State'
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': ['root']}
        folder = drive_service.files().create(body=metadata, fields='id').execute()
        return folder.get('id')

def load_state_from_drive(drive_service, folder_id):
    file_name = 'osint_state.json'
    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    
    if files:
        file_id = files[0]['id']
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        state_data = json.loads(fh.getvalue().decode('utf-8'))
        
        with open(LOCAL_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state_data, f)
        return state_data
    else:
        blank_state = {"processed_urls": []}
        with open(LOCAL_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(blank_state, f)
        return blank_state

# --- EXTRACTION & FETCHING ---
def extract_urls_from_markdown(md_path):
    log_action("[SYSTEM] Parsing Master Seed List for native endpoints...", LOG_FILE)
    urls = []
    if not os.path.exists(md_path):
        log_action(f"[FATAL] Could not find seed list at: {md_path}", LOG_FILE)
        return []

    with open(md_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Only pull from markdown table rows
            if line.strip().startswith('|') and 'http' in line:
                match = re.search(r'\]\((https?://[^\)]+)\)', line)
                if match:
                    urls.append(match.group(1).strip())
                else:
                    match_plain = re.search(r'(https?://[^\s\|]+)', line)
                    if match_plain:
                        urls.append(match_plain.group(1).strip())
                        
    unique_urls = list(set(urls))
    log_action(f"[SUCCESS] Extracted {len(unique_urls)} valid data endpoints.", LOG_FILE)
    return unique_urls

def extract_from_nested_json(data, seen_urls, source_url):
    """Recursively hunts for 'url' or 'link' keys anywhere in deeply nested APIs."""
    results = []
    
    def find_dicts(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from find_dicts(v)
        elif isinstance(node, list):
            for item in node:
                yield from find_dicts(item)

    for item in find_dicts(data):
        link = item.get('url') or item.get('link') or item.get('permalink')
        if link and isinstance(link, str) and link.startswith('http'):
            
            # Skip Reddit metadata links pointing back to subreddits/authors
            if 'reddit' in source_url and ('/user/' in link or '/r/' in link) and '/comments/' not in link:
                continue
                
            if link in seen_urls: continue
            
            title = item.get('title') or item.get('name') or item.get('headline') or "No Title"
            if len(str(title).strip()) < 5: continue
            
            summary = item.get('selftext') or item.get('description') or item.get('summary') or ""
            
            results.append({
                "title": str(title).strip(),
                "link": str(link).strip(),
                "source_feed": source_url,
                "summary_snippet": str(summary)[:500].strip()
            })
            seen_urls.add(link)
            
            # Cap at top 5 per feed to prevent queue flooding
            if len(results) >= 5:
                break
                
    return results

def run_fetcher_agent():
    log_action("\n" + "="*50, LOG_FILE)
    log_action("[AGENT 1] Booting The Fetcher (Unleashed + Cloudscraper)...", LOG_FILE)
    
    drive_service = authenticate_drive()
    folder_id = get_or_create_state_folder(drive_service)
    state = load_state_from_drive(drive_service, folder_id)
    seen_urls = set(state.get("processed_urls", []))
    
    feed_urls = extract_urls_from_markdown(SEED_LIST_PATH)
    if not feed_urls: return

    morning_intake = []
    
    # Initialize Cloudscraper to bypass Cloudflare
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    
    # NO SLICING. We execute all 288 endpoints.
    for url in feed_urls:
        log_action(f"  -> Polling: {url}", LOG_FILE)
        try:
            response = scraper.get(url, timeout=15)
            response.raise_for_status()
            
            content_type = response.headers.get('Content-Type', '').lower()
            
            # 1. JSON Processing
            if '.json' in url.lower() or 'json' in content_type:
                try:
                    data = response.json()
                    extracted = extract_from_nested_json(data, seen_urls, url)
                    if extracted:
                        morning_intake.extend(extracted)
                        for item in extracted:
                            log_action(f"     [NEW JSON] Queued: {item['title'][:60]}...", LOG_FILE)
                    else:
                        log_action("     [SKIP] No viable article links found in JSON.", LOG_FILE)
                except ValueError:
                    log_action("     [SKIP] Invalid JSON payload.", LOG_FILE)
                    
            # 2. XML / ATOM / RSS Processing
            else:
                feed = feedparser.parse(response.content)
                if not feed.entries:
                    log_action("     [SKIP] No entries or invalid XML.", LOG_FILE)
                    continue
                    
                for entry in feed.entries[:5]:
                    link = entry.get('link', '')
                    if not link or link in seen_urls: continue
                        
                    title = entry.get('title', 'No Title')
                    summary = entry.get('summary', '')[:500] 
                    
                    morning_intake.append({
                        "title": title,
                        "link": link,
                        "source_feed": url,
                        "summary_snippet": summary
                    })
                    seen_urls.add(link)
                    log_action(f"     [NEW XML] Queued: {title[:60]}...", LOG_FILE)
                    
        except Exception as e:
            # We catch and log all connection errors so a dead site doesn't crash the pipeline
            log_action(f"     [ERROR] Connection failed: {str(e)[:100]}", LOG_FILE)
            
    # Save the Intake Queue
    with open(INTAKE_QUEUE_PATH, 'w', encoding='utf-8') as f:
        json.dump(morning_intake, f, indent=4)
        
    state["processed_urls"] = list(seen_urls)
    with open(LOCAL_STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f)
    
    # Upload updated state back to Google Drive
    from googleapiclient.http import MediaFileUpload
    try:
        file_name = 'osint_state.json'
        query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        
        media = MediaFileUpload(LOCAL_STATE_PATH, mimetype='application/json')
        if files:
            file_id = files[0]['id']
            drive_service.files().update(fileId=file_id, media_body=media).execute()
        else:
            file_metadata = {'name': file_name, 'parents': [folder_id]}
            drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        log_action("[SYSTEM] Successfully synced state back to Google Drive.", LOG_FILE)
    except Exception as e:
        log_action(f"[ERROR] Failed to sync state to Google Drive: {e}", LOG_FILE)
        
    log_action(f"\n[SUCCESS] Agent 1 complete. Queued {len(morning_intake)} fresh articles for scoring.", LOG_FILE)
    log_action(f"[SYSTEM] Handoff ready at: {INTAKE_QUEUE_PATH}", LOG_FILE)

if __name__ == "__main__":
    run_fetcher_agent()