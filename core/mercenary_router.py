import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import random
import requests
import asyncio
import uuid
import gc
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'secrets', '.env'))

app = FastAPI(title="DSIE Mercenary Router")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "https://thedsiecodex.online",
        "tauri://localhost",
        "http://tauri.localhost",
        "*"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bridge to DSIE Core
from dsie_core import DSIECore
_dsie = None

def get_dsie():
    global _dsie
    if _dsie is None:
        _dsie = DSIECore()
        _dsie.load_hardware()
    return _dsie

async def process_background_task(task_id: str, prompt: str):
    """Worker function for asynchronous NPU-Cloud handoff."""
    try:
        core = get_dsie()
        # The prompt is processed through the standard pipeline (Local -> MCP -> Vanguard)
        reply = core.process_text(prompt)
        # Ensure the final result is pushed with the Vanguard tag
        core.push_transcript("Codex", f"[Vanguard-Result] (ID: {task_id}) {reply}")
    except Exception as e:
        print(f"[BACKGROUND ERROR] Task {task_id} failed: {e}")
    finally:
        gc.collect()

class PromptRequest(BaseModel):
    prompt: str

class ChatRequest(BaseModel):
    provider: str
    model: str
    messages: list
    temperature: float = 0.2
    response_format: dict = None

PROVIDERS = {
    "Cerebras Cloud": {"url": "https://api.cerebras.ai/v1/chat/completions", "env_key": "CEREBRAS_API_KEY"},
    "GroqCloud": {"url": "https://api.groq.com/openai/v1/chat/completions", "env_key": "GROQ_API_KEY"},
    "SambaNova Cloud": {"url": "https://api.sambanova.ai/v1/chat/completions", "env_key": "SAMBANOVA_API_KEY"},
    "Google AI Studio": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "env_key": "GOOGLE_API_KEY"},
    "Mistral AI": {"url": "https://api.mistral.ai/v1/chat/completions", "env_key": "MISTRAL_API_KEY"},
    "xAI": {"url": "https://api.x.ai/v1/chat/completions", "env_key": "XAI_API_KEY"},
    "NVIDIA NIM": {"url": "https://integrate.api.nvidia.com/v1/chat/completions", "env_key": "NVIDIA_API_KEY"},
    "OpenRouter": {"url": "https://openrouter.ai/api/v1/chat/completions", "env_key": "OPENROUTER_API_KEY"},
    "Cloudflare Workers AI": {"url": f"https://api.cloudflare.com/client/v4/accounts/{os.getenv('CLOUDFLARE_ACCOUNT_ID')}/ai/v1/chat/completions", "env_key": "CLOUDFLARE_API_KEY"},
    "Hugging Face": {"url": "https://api-inference.huggingface.co/v1/chat/completions", "env_key": "HUGGINGFACE_API_KEY"},
    "GitHub Models": {"url": "https://models.inference.ai.azure.com/chat/completions", "env_key": "GITHUB_API_KEY"},
    "Together AI": {"url": "https://api.together.xyz/v1/chat/completions", "env_key": "TOGETHER_API_KEY"},
    "Fireworks AI": {"url": "https://api.fireworks.ai/inference/v1/chat/completions", "env_key": "FIREWORKS_API_KEY"},
    "DeepInfra": {"url": "https://api.deepinfra.com/v1/openai/chat/completions", "env_key": "DEEPINFRA_API_KEY"},
    "Novita AI": {"url": "https://api.novita.ai/v3/openai/chat/completions", "env_key": "NOVITA_API_KEY"},
    "Cohere": {"url": "https://api.cohere.ai/v1/chat/completions", "env_key": "COHERE_API_KEY"},
    "CometAPI": {"url": "https://api.cometapi.com/v1/chat/completions", "env_key": "COMET_API_KEY"},
    "Z.ai": {"url": "https://api.z.ai/v1/chat/completions", "env_key": "ZAI_API_KEY"},
    "Moonshot AI": {"url": "https://api.moonshot.cn/v1/chat/completions", "env_key": "MOONSHOT_API_KEY"},
    "OpenCode Zen": {"url": "https://api.opencode.ai/v1/chat/completions", "env_key": "OPENCODE_ZEN_API_KEY"},
    "Arcee AI": {"url": "https://api.arcee.ai/v1/chat/completions", "env_key": "ARCEE_API_KEY"}
}

DEFAULT_MODELS = {
    "Cerebras Cloud": "llama-4-scout-17b-16e-instruct",
    "GroqCloud": "llama-3.3-70b-versatile",
    "SambaNova Cloud": "Meta-Llama-3.3-70B-Instruct",
    "Google AI Studio": "gemini-3-flash-preview",
    "Mistral AI": "mistral-small-latest",
    "xAI": "grok-3-mini-fast",
    "NVIDIA NIM": "meta/llama-3.3-70b-instruct",
    "OpenRouter": "google/gemini-2.5-flash",
    "Cloudflare Workers AI": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "Hugging Face": "Qwen/Qwen2.5-72B-Instruct",
    "GitHub Models": "gpt-4o-mini",
    "Together AI": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "Fireworks AI": "accounts/fireworks/models/llama4-scout-instruct-basic",
    "DeepInfra": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
    "Novita AI": "meta-llama/llama-3.3-70b-instruct",
    "Cohere": "command-a-03-2025",
    "CometAPI": "gpt-4o-mini",
    "Z.ai": "z1-small",
    "Moonshot AI": "moonshot-v1-auto",
    "OpenCode Zen": "opencode-zen",
    "Arcee AI": "arcee-blitz",
}

@app.get("/providers")
def list_providers():
    result = []
    for name, config in PROVIDERS.items():
        has_key = bool(os.getenv(config["env_key"]))
        result.append({
            "provider": name,
            "active": has_key,
            "default_model": DEFAULT_MODELS.get(name, "default"),
        })
    return {"providers": result}

def execute_request_with_backoff(url, headers, payload, max_retries=4):
    """Shields upstream local agents from transient cloud failures."""
    base_delay = 1
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            if response.status_code in [429, 503]:
                response.raise_for_status() 
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            is_rate_limit = False
            if e.response is not None and e.response.status_code in [429, 503]:
                is_rate_limit = True
                
            if attempt == max_retries - 1:
                error_msg = e.response.text if e.response is not None else str(e)
                raise HTTPException(status_code=500, detail=f"Provider Connection Failed after {max_retries} retries: {error_msg}")
                
            if is_rate_limit:
                jitter = random.uniform(0, 1)
                delay = (base_delay * (2 ** attempt)) + jitter
                print(f"[ROUTER THROTTLE] Waiting {delay:.2f}s before retry...")
                time.sleep(delay)
            else:
                error_msg = e.response.text if e.response is not None else str(e)
                raise HTTPException(status_code=e.response.status_code if e.response else 500, detail=f"Provider Error: {error_msg}")

@app.post("/chat")
def route_chat(req: ChatRequest):
    if req.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")
    
    provider_config = PROVIDERS[req.provider]
    api_key = os.getenv(provider_config["env_key"])
    
    if not api_key:
        raise HTTPException(status_code=401, detail=f"Missing API key in .env for {req.provider}.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    if req.provider == "OpenRouter":
        headers["HTTP-Referer"] = "http://127.0.0.1:8090"
        headers["X-Title"] = "DSIE Codex Core"

    payload = {
        "model": req.model,
        "messages": req.messages,
        "temperature": req.temperature
    }
    
    if req.response_format:
        payload["response_format"] = req.response_format

    return execute_request_with_backoff(provider_config["url"], headers, payload)

@app.post("/api/chat")
async def omni_chat(req: PromptRequest, background_tasks: BackgroundTasks):
    """Bridges the UI input area to the local DSIE Core inference engine."""
    prompt = req.prompt
    triggers = ["deep", "scrape", "background", "queue", "asynchronous"]
    
    if any(t in prompt.lower() for t in triggers):
        task_id = str(uuid.uuid4())[:8]
        core = get_dsie()
        
        # 1. Immediate ACK to PocketBase and TTS
        ack_msg = f"[Queue-Active] Task {task_id} dispatched. Awaiting background resolution..."
        core.push_transcript("Codex", ack_msg)
        core.speak("Dispatching task to the background queue.")
        
        # 2. Hand off to background worker
        background_tasks.add_task(process_background_task, task_id, prompt)
        
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=202, content={"status": "accepted", "task_id": task_id})

    try:
        core = get_dsie()
        # process_text handles PocketBase pushes and TTS natively
        reply = core.process_text(prompt)
        return {"status": "success", "reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/briefs")
def get_briefs():
    import json
    # Look in dashboard/ui first, then dashboard
    path_ui = os.path.join(os.path.dirname(__file__), "..", "dashboard", "ui", "consolidated_briefs.json")
    path_root = os.path.join(os.path.dirname(__file__), "..", "dashboard", "consolidated_briefs.json")
    
    for briefs_path in [path_ui, path_root]:
        if os.path.exists(briefs_path):
            with open(briefs_path, "r", encoding="utf-8") as f:
                return json.load(f)
    return []

if __name__ == "__main__":
    import uvicorn
    print("[SYSTEM] Booting DSIE Mercenary Router on Port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)