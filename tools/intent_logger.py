import json
import os
from datetime import datetime

LOG_FILE = r"Z:\foundry_project\logs\intent_history.json"

def log_intent(prompt: str, decision: str):
    """
    Appends a routing decision to the intent history log.
    Decision should be 'Local' or 'Cloud'.
    """
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "decision": decision
    }
    
    # Read existing data or start new list
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = []
    else:
        data = []
    
    data.append(entry)
    
    # Write back with indentation
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        log_intent(sys.argv[1], sys.argv[2])
