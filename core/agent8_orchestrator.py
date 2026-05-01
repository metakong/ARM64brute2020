import os
import sys
import json
import time
import socket
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CORE_DIR = BASE_DIR / 'core'

load_dotenv(str(BASE_DIR / 'secrets' / '.env'))

LOG_FILE = str(BASE_DIR / 'logs' / 'agent8_orchestrator_log.txt')
SERVICE_ACCOUNT_FILE = os.getenv('GCP_SERVICE_KEY')
POCKETBASE_URL = "http://127.0.0.1:8090"

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log_action(message):
    print(message)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")


# =============================================================================
# PHASE 0: ENVIRONMENT BINDING & INFRASTRUCTURE CHECKS
# =============================================================================
def resolve_python_executable():
    """Resolve the correct Python binary: prefer local .venv, fallback to sys.executable."""
    venv_python = BASE_DIR / 'venv' / 'Scripts' / 'python.exe'
    if venv_python.exists():
        log_action(f"[ENV] Local .venv detected: {venv_python}")
        return str(venv_python)
    else:
        log_action(f"[ENV] No local .venv found. Using sys.executable: {sys.executable}")
        return sys.executable

def check_and_start_pocketbase():
    """Ensure PocketBase is running on port 8090 before the pipeline starts."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(2)
        sock.connect(('127.0.0.1', 8090))
        sock.close()
        log_action("[INFRA] PocketBase is already running on port 8090.")
        return
    except (ConnectionRefusedError, OSError, socket.timeout):
        sock.close()

    pb_exe = BASE_DIR / 'bus' / 'pocketbase' / 'pocketbase.exe'
    if not pb_exe.exists():
        log_action(f"[WARNING] PocketBase executable not found at: {pb_exe}")
        log_action("[WARNING] Skipping auto-boot. Pipeline may fail on DB writes.")
        return

    log_action("[INFRA] PocketBase was down. Auto-booting...")
    subprocess.Popen(
        [str(pb_exe), 'serve'],
        cwd=str(pb_exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    )
    
    # Active PocketBase Polling
    start_time = time.time()
    while True:
        try:
            resp = requests.get('http://127.0.0.1:8090/api/health', timeout=1)
            if resp.status_code == 200:
                log_action("[INFRA] PocketBase boot sequence complete. Proceeding.")
                return
        except Exception:
            pass
            
        if time.time() - start_time > 15:
            log_action("[FATAL] PocketBase failed to start within 15 seconds. Aborting pipeline.")
            sys.exit(1)
            
        time.sleep(0.5)


# =============================================================================
# PHASE 1: SEQUENTIAL AGENT PIPELINE
# =============================================================================
AGENT_CHAIN = [
    ("Agent 1 (Fetcher)",      str(CORE_DIR / 'agent1_fetcher.py')),
    ("Agent 2 (Scorer)",       str(CORE_DIR / 'agent2_scorer.py')),
    ("Agent 3 (Extractor)",    str(CORE_DIR / 'agent3_extractor.py')),
    ("Agent 4 (Consolidator)", str(CORE_DIR / 'agent4_consolidator.py')),
    ("Agent 5 (Creator)",      str(CORE_DIR / 'agent5_content_creator.py')),
    ("Agent 6 (Injector)",     str(CORE_DIR / 'agent6_dashboard_injector.py')), # RESTORED
    ("Agent 7 (Historian)",    str(CORE_DIR / 'agent7_evolutionary_historian.py')),
]

def run_agent_chain():
    """Execute each agent sequentially. Halt on first failure."""
    python_exe = resolve_python_executable()

    log_action("\n" + "="*60)
    log_action("[ORCHESTRATOR] Initiating Sequential Agent Pipeline...")
    log_action(f"[ORCHESTRATOR] Python Executable: {python_exe}")

    for agent_name, agent_path in AGENT_CHAIN:
        log_action(f"\n--- Executing: {agent_name} ---")
        start = time.time()

        # FIX: Removed capture_output=True. This allows the sub-agents' print() 
        # statements to stream directly to your PowerShell window in real-time.
        result = subprocess.run(
            [python_exe, agent_path],
            cwd=str(BASE_DIR)
        )

        elapsed = time.time() - start

        if result.returncode != 0:
            log_action(f"[FATAL] {agent_name} FAILED (exit code {result.returncode}) after {elapsed:.1f}s")
            log_action("[ORCHESTRATOR] Pipeline HALTED. Fix the failing agent and re-run.")
            return False
        else:
            log_action(f"[SUCCESS] {agent_name} completed in {elapsed:.1f}s")

    log_action("\n[ORCHESTRATOR] Full agent chain completed successfully.")
    return True


# =============================================================================
# PHASE 2: GOOGLE DRIVE ARCHIVAL & SSD PROTECTION (72-HOUR ROLLING WINDOW)
# =============================================================================
ARCHIVE_COLLECTIONS = ["transcripts", "vault"]

def get_cutoff_iso():
    """Return ISO timestamp for 72 hours ago."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    return cutoff.strftime('%Y-%m-%d %H:%M:%S')

def query_old_pocketbase_records(collection, cutoff_iso):
    """Query PocketBase for records older than the cutoff."""
    records = []
    page = 1
    while True:
        try:
            resp = requests.get(
                f"{POCKETBASE_URL}/api/collections/{collection}/records",
                params={
                    "filter": f'created < "{cutoff_iso}"',
                    "page": page,
                    "perPage": 200,
                },
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break
            records.extend(items)
            if page >= data.get("totalPages", 1):
                break
            page += 1
        except Exception as e:
            log_action(f"  [ERROR] PocketBase query failed for {collection}: {e}")
            break
    return records

def authenticate_gdrive():
    """Authenticate to Google Drive using the service account key."""
    if not SERVICE_ACCOUNT_FILE or not os.path.exists(SERVICE_ACCOUNT_FILE):
        log_action("[WARNING] GCP_SERVICE_KEY not set or file missing. Skipping Drive archival.")
        return None
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def get_or_create_archive_folder(drive_service):
    """Find or create the DSIE_Archives folder in Google Drive."""
    folder_name = "DSIE_Archives"
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    folder = drive_service.files().create(body=metadata, fields='id').execute()
    log_action(f"  [NEW FOLDER] Created '{folder_name}' in Google Drive.")
    return folder.get('id')

def upload_to_gdrive(drive_service, folder_id, local_path, filename):
    """Upload a JSON file to the DSIE_Archives folder. Returns True on success."""
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaFileUpload(local_path, mimetype='application/json')
    uploaded = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    return uploaded.get('id') is not None

def delete_pocketbase_records(collection, record_ids):
    """Delete records from PocketBase by ID."""
    deleted = 0
    for rid in record_ids:
        try:
            resp = requests.delete(
                f"{POCKETBASE_URL}/api/collections/{collection}/records/{rid}",
                timeout=5
            )
            if resp.status_code in [200, 204]:
                deleted += 1
        except Exception:
            pass
    return deleted

def run_rolling_archive():
    """Archive old PocketBase records to Google Drive, then purge local copies."""
    log_action("\n" + "="*60)
    log_action("[ORCHESTRATOR] Initiating 72-Hour Rolling Window Archive...")

    drive_service = authenticate_gdrive()
    if not drive_service:
        return

    cutoff_iso = get_cutoff_iso()
    log_action(f"  Cutoff Timestamp: {cutoff_iso}")

    folder_id = get_or_create_archive_folder(drive_service)

    for collection in ARCHIVE_COLLECTIONS:
        log_action(f"\n  --- Processing collection: {collection} ---")
        old_records = query_old_pocketbase_records(collection, cutoff_iso)

        if not old_records:
            log_action(f"  No records older than 72h in '{collection}'. Skipping.")
            continue

        log_action(f"  Found {len(old_records)} records to archive.")

        archive_dir = str(BASE_DIR / 'logs')
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        archive_filename = f"archive_{collection}_{timestamp}.json"
        temp_path = os.path.join(archive_dir, archive_filename)

        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(old_records, f, indent=2)
        log_action(f"  Exported to: {temp_path}")

        try:
            success = upload_to_gdrive(drive_service, folder_id, temp_path, archive_filename)
        except Exception as e:
            log_action(f"  [FATAL] Google Drive upload failed: {e}")
            log_action(f"  Local archive preserved at: {temp_path}")
            continue

        if not success:
            log_action(f"  [FATAL] Upload returned no file ID. Local archive preserved.")
            continue

        log_action(f"  [SUCCESS] Uploaded {archive_filename} to Google Drive.")

        record_ids = [r['id'] for r in old_records]
        deleted = delete_pocketbase_records(collection, record_ids)
        log_action(f"  [PURGED] Deleted {deleted}/{len(record_ids)} records from local PocketBase.")

        try:
            os.remove(temp_path)
            log_action(f"  [CLEANUP] Removed temporary archive file.")
        except Exception:
            pass

    log_action("\n[ORCHESTRATOR] Rolling archive cycle complete.")


# =============================================================================
# PHASE 3: SCRATCH SPACE PURGE (LOCAL SSD PROTECTION)
# =============================================================================
def cleanup_scratch_space():
    """Safely delete massive temporary JSON files generated during the pipeline run."""
    log_action("\n" + "="*60)
    log_action("[ORCHESTRATOR] Initiating Scratch Space Purge (--cleanup flag detected)")
    
    # List of ephemeral files that are no longer needed once the pipeline finishes
    files_to_purge = [
        BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'atomic_facts_log.json',
        BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'agent5_content_staging.json',
        BASE_DIR / 'dashboard' / 'OSINT_System_State' / 'scored_intake_log.json',
        BASE_DIR / 'dashboard' / 'consolidated_briefs.json'
    ]

    bytes_freed = 0
    for target in files_to_purge:
        if target.exists():
            try:
                size = target.stat().st_size
                target.unlink()
                bytes_freed += size
                log_action(f"  [DELETED] {target.name} ({(size / 1024 / 1024):.2f} MB)")
            except Exception as e:
                log_action(f"  [ERROR] Failed to delete {target.name}: {e}")
        else:
            log_action(f"  [SKIPPED] {target.name} not found.")

    log_action(f"[SUCCESS] Scratch space purged. Freed {(bytes_freed / 1024 / 1024):.2f} MB.")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def main():
    log_action("\n" + "#"*60)
    log_action(f"[ORCHESTRATOR] DSIE Codex Pipeline - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log_action("#"*60)

    # Phase 0: Infrastructure checks
    check_and_start_pocketbase()

    # Determine if we run the full pipeline or just cleanup
    run_pipeline = "--cleanup-only" not in sys.argv
    do_cleanup = "--cleanup" in sys.argv or "--cleanup-only" in sys.argv

    if run_pipeline:
        # Phase 1: Run the agent chain
        pipeline_ok = run_agent_chain()
        if not pipeline_ok:
            log_action("[ORCHESTRATOR] Skipping archival & cleanup due to pipeline failure.")
            return

    # Phase 2: Archive and purge old data
    run_rolling_archive()

    # Phase 3: Hardware Protection (Execute if flag was passed)
    if do_cleanup:
        cleanup_scratch_space()

    log_action("\n[ORCHESTRATOR] All phases complete. System idle.")

if __name__ == "__main__":
    main()