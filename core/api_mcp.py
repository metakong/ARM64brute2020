import gc
import json
import os
import sys
import urllib.request
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Initialize FastMCP server named "Cloud_Vanguard"
mcp = FastMCP("Cloud_Vanguard")

@mcp.tool()
def delegate_to_gemini(task_description: str) -> str:
    """
    Delegates complex reasoning, coding, or deep analysis tasks to the Gemini 3 Flash model.
    """
    # Scope-bound environment loading for security
    env_path = Path(__file__).resolve().parent.parent / 'secrets' / '.env'
    load_dotenv(str(env_path))
    api_key = os.getenv('GOOGLE_API_KEY') # Using standard key name from project
    
    if not api_key:
        return "Error: GOOGLE_API_KEY not found in secrets/.env"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": task_description}]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048
        }
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            # Extract text from Gemini response structure
            try:
                reply = result['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                reply = f"Error: Unexpected response format. Raw: {json.dumps(result)}"
            
            res = reply
    except Exception as e:
        res = f"Error during Gemini delegation: {str(e)}"
    
    # SOP-01: Compliance with memory strict protocols
    gc.collect()
    
    return res

if __name__ == "__main__":
    print("Booting DSIE Cloud Vanguard on stdio...", file=sys.stderr)
    mcp.run(transport='stdio')
