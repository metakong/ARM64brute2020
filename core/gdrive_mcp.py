import os
import sys
import time
import random
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from dsie_utils import execute_with_backoff

dotenv_path = str(Path(__file__).resolve().parent.parent / 'secrets' / '.env')
load_dotenv(dotenv_path=dotenv_path)

SERVICE_ACCOUNT_FILE = os.getenv('GCP_SERVICE_KEY')

print(f"[DEBUG] .env path: {dotenv_path}", file=sys.stderr)
print(f"[DEBUG] Key path from env: {SERVICE_ACCOUNT_FILE}", file=sys.stderr)

if not SERVICE_ACCOUNT_FILE or not os.path.exists(SERVICE_ACCOUNT_FILE):
    print(f"[FATAL] GCP_SERVICE_KEY variable missing or invalid: {SERVICE_ACCOUNT_FILE}", file=sys.stderr)
    sys.exit(1)

try:
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    drive_service = build('drive', 'v3', credentials=creds)
    print("[DEBUG] Google API Authorized Successfully", file=sys.stderr)
except Exception as e:
    print(f"Error initializing Google Auth: {e}", file=sys.stderr)
    sys.exit(1)

mcp = FastMCP("GoogleDriveVault")

@mcp.tool()
def search_drive(query: str) -> str:
    """Search for files in the authorized Google Drive folder."""
    # FAILSAGE: Prevent Drive API crash on unescaped quotes
    safe_query = query.replace("'", "\\'")
    
    def _search():
        return drive_service.files().list(q=f"name contains '{safe_query}' and trashed = false", spaces='drive').execute()
        
    try:
        results = execute_with_backoff(_search)
        files = results.get('files', [])
        if not files:
            return "No files found."
        return "\n".join([f"ID: {f['id']} - Name: {f['name']}" for f in files])
    except Exception as e:
        return f"Error executing search: {e}"

@mcp.tool()
def fetch_business_sop(topic: str) -> str:
    """Retrieves business rules, SOPs, or templates from Google Drive based on a topic."""
    # Targeted query for SOP/Template and the topic
    safe_topic = topic.replace("'", "\\'")
    query = f"(name contains 'SOP' or name contains 'Template') and name contains '{safe_topic}' and trashed = false"
    
    try:
        results = drive_service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if not files:
            return f"No SOP or Template found for topic: {topic}"
            
        # Get content of the first match (assuming most relevant)
        file_id = files[0]['id']
        file_name = files[0]['name']
        
        # Download file content
        content = drive_service.files().get_media(fileId=file_id).execute().decode('utf-8')
        return f"--- DOCUMENT: {file_name} ---\n{content}"
        
    except Exception as e:
        return f"Error fetching SOP: {e}"

if __name__ == "__main__":
    mcp.run()