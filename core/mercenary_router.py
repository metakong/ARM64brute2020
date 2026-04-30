import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load keys from the hidden .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

app = FastAPI(title="DSIE Mercenary Router")

# Allow the local HTML dashboard to talk to this Python server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    provider: str
    model: str
    messages: list
    temperature: float = 0.2

# The master routing table
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

# Default models per provider for the dashboard dropdown
DEFAULT_MODELS = {
    "Cerebras Cloud": "llama-4-scout-17b-16e-instruct",
    "GroqCloud": "llama-3.3-70b-versatile",
    "SambaNova Cloud": "Meta-Llama-3.3-70B-Instruct",
    "Google AI Studio": "gemini-2.5-flash",
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
    """Returns all providers, their key status, and default model."""
    result = []
    for name, config in PROVIDERS.items():
        has_key = bool(os.getenv(config["env_key"]))
        result.append({
            "provider": name,
            "active": has_key,
            "default_model": DEFAULT_MODELS.get(name, "default"),
        })
    return {"providers": result}

@app.post("/chat")
def route_chat(req: ChatRequest):
    if req.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")
    
    provider_config = PROVIDERS[req.provider]
    api_key = os.getenv(provider_config["env_key"])
    
    if not api_key:
        raise HTTPException(status_code=401, detail=f"Missing API key in .env for {req.provider}. Variable {provider_config['env_key']} is empty.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # Mandatory anti-abuse headers for OpenRouter
    if req.provider == "OpenRouter":
        headers["HTTP-Referer"] = "http://127.0.0.1:8090"
        headers["X-Title"] = "DSIE Codex Core"

    payload = {
        "model": req.model,
        "messages": req.messages,
        "temperature": req.temperature
    }

    try:
        response = requests.post(provider_config["url"], headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        error_msg = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=500, detail=f"Provider Connection Failed: {error_msg}")

if __name__ == "__main__":
    import uvicorn
    print("[SYSTEM] Booting DSIE Mercenary Router on Port 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)