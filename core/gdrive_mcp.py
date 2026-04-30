import os
import sys
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Force load from project root (relative to this script)
dotenv_path = str(Path(__file__).resolve().parent.parent / '.env')
load_dotenv(dotenv_path=dotenv_path)

SERVICE_ACCOUNT_FILE = os.getenv('GCP_SERVICE_KEY')

# DEBUG: See what the script actually caught
print(f"[DEBUG] .env path: {dotenv_path}", file=sys.stderr)
print(f"[DEBUG] Key path from env: {SERVICE_ACCOUNT_FILE}", file=sys.stderr)

if not SERVICE_ACCOUNT_FILE:
    print("Error: GCP_SERVICE_KEY variable not found in .env", file=sys.stderr)
    sys.exit(1)

if not os.path.exists(SERVICE_ACCOUNT_FILE):
    print(f"Error: File does not exist at path: {SERVICE_ACCOUNT_FILE}", file=sys.stderr)
    sys.exit(1)

# Initialize Google Drive API
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
    results = drive_service.files().list(q=f"name contains '{query}'", spaces='drive').execute()
    files = results.get('files', [])
    if not files:
        return "No files found."
    return "\n".join([f"ID: {f['id']} - Name: {f['name']}" for f in files])

if __name__ == "__main__":
    mcp.run()