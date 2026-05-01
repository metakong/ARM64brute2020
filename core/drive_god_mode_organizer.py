import os
import sys
import json
import time
import random
import shutil
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from dotenv import load_dotenv

from dsie_utils import log_action, execute_with_backoff, clean_json_response, GEMINI_MODEL

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(str(BASE_DIR / '.env'))
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)

SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_SECRET_FILE = str(BASE_DIR / 'secrets' / 'client_secret.json')
TOKEN_FILE = str(BASE_DIR / 'secrets' / 'token.json')
STATE_FILE = str(BASE_DIR / 'organizer_state.json')
LOG_FILE = str(BASE_DIR / 'logs' / 'organizer_log.txt')
BATCH_SIZE = 100

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def load_state():
    """Loads the category memory. Initializes with the Catch-All folder."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            log_action("[WARNING] State file corrupted. Building new state.", LOG_FILE)
            
    return {"categories": {"Uncategorized": None}}

def save_state(state):
    """Atomically saves state so Ctrl+C doesn't corrupt the JSON."""
    temp_file = STATE_FILE + '.tmp'
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=4)
    shutil.move(temp_file, STATE_FILE)

def authenticate_god_mode():
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

def get_root_files_batch(drive_service, ignore_ids):
    """Pulls one batch of files from the root directory, explicitly ignoring poisoned IDs."""
    query = "'root' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'"
    
    if ignore_ids:
        for fid in ignore_ids:
            query += f" and not id = '{fid}'"
            
    def _fetch():
        results = drive_service.files().list(
            q=query, 
            pageSize=BATCH_SIZE, 
            fields="files(id, name, parents)"
        ).execute()
        return results.get('files', [])
        
    return execute_with_backoff(_fetch)

def get_gemini_mapping(files, current_categories):
    """Sends the file batch and the conversation history (categories) to Gemini."""
    file_list_str = "\n".join([f"{f['id']} | {f['name']}" for f in files])
    existing_cats_str = ", ".join(current_categories)
    
    prompt = f"""
    You are an expert taxonomy AI organizing a user's 16-year Google Drive archive.
    
    Here is the current batch of {len(files)} files:
    {file_list_str}
    
    Here is your "Conversation History" - the categories you have ALREADY created:
    [{existing_cats_str}]
    
    YOUR DIRECTIVES:
    1. Assign each file to a category based on its name.
    2. STRONGLY PREFER sorting files into the EXISTING categories listed above to prevent redundancy.
    3. If a file clearly requires a NEW category, invent a broad, highly organized top-level folder name (e.g., 'Financials', 'Client_Contracts').
    4. CATCH-ALL RULE: If a file name is random nonsense (e.g., 'scan_001', 'untitled_3'), completely unidentifiable, or lacks context, assign it strictly to the category "Uncategorized".
    
    Return ONLY a raw JSON dictionary where the Key is the File ID, and the Value is the Category Name.
    """
    
    def _generate():
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        safe_text = clean_json_response(response.text)
        return json.loads(safe_text)
        
    return execute_with_backoff(_generate)

def get_or_create_folder(drive_service, category_name, state):
    """Checks state memory for the folder. If missing, creates it in Drive and updates state."""
    if category_name in state['categories'] and state['categories'][category_name]:
        return state['categories'][category_name]
    
    def _create():
        safe_name = category_name.replace("'", "\\'")
        query = f"name='{safe_name}' and mimeType='application/vnd.google-apps.folder' and 'root' in parents and trashed=false"
        existing = drive_service.files().list(q=query, spaces='drive').execute().get('files', [])
        
        if existing:
            return existing[0]['id']
            
        metadata = {'name': category_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': ['root']}
        folder = drive_service.files().create(body=metadata, fields='id').execute()
        folder_id = folder.get('id')
        log_action(f"  [NEW FOLDER] Created category: {category_name}", LOG_FILE)
        return folder_id

    folder_id = execute_with_backoff(_create)
    state['categories'][category_name] = folder_id
    save_state(state)
    return folder_id

def move_file(drive_service, file_id, new_folder_id, previous_parents_list):
    """Safely moves a file by explicitly removing old parents. Uses cached parents to save 1 API call."""
    def _move():
        previous_parents = ",".join(previous_parents_list)
        
        drive_service.files().update(
            fileId=file_id,
            addParents=new_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        
    execute_with_backoff(_move)

def run_organizer():
    log_action("\n" + "="*50, LOG_FILE)
    log_action("[SYSTEM] Booting Stateful Drive Organizer (God Mode + Backoff)...", LOG_FILE)
    
    drive_service = authenticate_god_mode()
    state = load_state()
    batch_count = 1
    poisoned_files = [] 
    
    while True:
        log_action(f"\n[SYSTEM] Fetching Batch #{batch_count}...", LOG_FILE)
        files = get_root_files_batch(drive_service, poisoned_files)
        
        if not files:
            log_action("[SUCCESS] No loose files remain in root. Organization Complete.", LOG_FILE)
            if poisoned_files:
                log_action(f"[INFO] Ignored {len(poisoned_files)} unmovable/ghost files during processing.", LOG_FILE)
            break
            
        try:
            current_cats = list(state['categories'].keys())
            mapping = get_gemini_mapping(files, current_cats)
            
            for file_id, category_name in mapping.items():
                valid_file = next((f for f in files if f['id'] == file_id), None)
                if not valid_file:
                    log_action(f"  [WARNING] Gemini hallucinated ID: {file_id}. Skipping.", LOG_FILE)
                    continue
                    
                try:
                    folder_id = get_or_create_folder(drive_service, category_name, state)
                    parents = valid_file.get('parents', ['root'])
                    move_file(drive_service, file_id, folder_id, parents)
                    log_action(f"  Moved: '{valid_file['name'][:40]}' -> [{category_name}]", LOG_FILE)
                except HttpError as e:
                    if e.resp.status in [404, 403]:
                        log_action(f"  [WARNING] File restricted/ghosted: '{valid_file['name'][:40]}'. Adding to ignore list.", LOG_FILE)
                        poisoned_files.append(file_id)
                        continue
                    else:
                        raise e 
                        
        except Exception as e:
            log_action(f"[FATAL BATCH ERROR] {e}. Skipping batch to prevent infinite loop.", LOG_FILE)
            poisoned_files.extend([f['id'] for f in files])
            
        batch_count += 1
        save_state(state)
        time.sleep(2)

if __name__ == "__main__":
    run_organizer()