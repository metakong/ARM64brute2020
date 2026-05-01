import os
import sys
import subprocess
import time
import datetime
import re
import json
import requests
import numpy as np
import wave
import sounddevice as sd
from pathlib import Path

# Native Cloud Integration
from dotenv import load_dotenv
from google import genai
from google.genai import types

# MCP Nexus Integration
import asyncio
import gc
from mcp_nexus import initialize_nexus, call_mcp_tool, get_tools_for_llm, shutdown_nexus

BASE_DIR = Path(__file__).resolve().parent.parent

# 1. Map Cache & Ephemeral Storage (SSD Protection)
os.environ["FOUNDRY_LOCAL_CACHE_DIR"] = r"Z:\foundry_cache"
os.environ["TEMP"] = r"Z:\SystemTemp"
os.environ["TMP"] = r"Z:\SystemTemp"

# 2. HARD-LINK QUALCOMM HEXAGON NPU BINARIES (QAIRT)
qairt_lib = r"Z:\QCDrivers\qairt\2.45.0.260326\lib\arm64x-windows-msvc"
qairt_bin = r"Z:\QCDrivers\qairt\2.45.0.260326\bin\arm64x-windows-msvc"

if os.path.exists(qairt_lib):
    os.add_dll_directory(qairt_lib)
    os.environ["PATH"] = qairt_lib + os.pathsep + os.environ["PATH"]
if os.path.exists(qairt_bin):
    os.add_dll_directory(qairt_bin)
    os.environ["PATH"] = qairt_bin + os.pathsep + os.environ["PATH"]
    
os.environ["QAIRT_SDK_ROOT"] = r"Z:\QCDrivers\qairt\2.45.0.260326"

from foundry_local_sdk import Configuration, FoundryLocalManager
from foundry_local_sdk.logging_helper import LogLevel

POWERSHELL_EXE = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
TEMP_WAV_PATH = str(BASE_DIR / 'logs' / 'temp_input.wav')

def get_optimal_mic_index():
    devices = sd.query_devices()
    samson_idx = next((i for i, d in enumerate(devices) if "Samson Q2U" in d['name'] and d['max_input_channels'] > 0), None)
    if samson_idx is not None:
        print(f"--- [AUDIO] Samson Q2U detected at index {samson_idx}. Using pro input.")
        return samson_idx
    internal_idx = next((i for i, d in enumerate(devices) if "Internal Microphone" in d['name'] and d['max_input_channels'] > 0), None)
    return internal_idx

class DSIECore:
    def __init__(self):
        print("[SYSTEM] Booting DSIE Codex Core (NPU FORCED VIA GLOBAL CONFIG)...")
        log_path = r"Z:\foundry_project\logs"
        os.makedirs(log_path, exist_ok=True)
        
        # Load API keys natively to bypass external router dependence for the voice engine
        load_dotenv(str(BASE_DIR / 'secrets' / '.env'))
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        if self.google_api_key:
            self.gemini_client = genai.Client(api_key=self.google_api_key)
        else:
            print("[WARNING] GOOGLE_API_KEY not found in .env. Cloud handoff disabled.")
            self.gemini_client = None
        
        config = Configuration(
            app_name="dsie_codex",
            model_cache_dir=r"Z:\foundry_cache\models",
            logs_dir=log_path,
            log_level=LogLevel.VERBOSE,
            additional_settings={
                "ExecutionProvider": "QnnExecutionProvider",
                "EpDetectorOverride": "true"
            }
        )
        
        FoundryLocalManager.initialize(config)
        self.manager = FoundryLocalManager.instance
        
        self.mic_index = get_optimal_mic_index()
        self.llm_model = None
        self.whisper_model = None
        
        # Initialize MCP Nexus Connections
        asyncio.run(initialize_nexus())

    def load_hardware(self):
        print("[SYSTEM] Syncing Models with Native SDK Registry...")
        try:
            print(" -> Syncing Qwen to Hexagon NPU...")
            self.llm_model = self.manager.catalog.get_model("qwen2.5-0.5b")
            
            if self.llm_model is None:
                raise Exception("Model not found in catalog. Check network connection.")
                
            self.llm_model.load()
            self.chat_client = self.llm_model.get_chat_client()

            print(" -> Syncing Whisper to Hexagon NPU...")
            self.whisper_model = self.manager.catalog.get_model("whisper-tiny")
            if not self.whisper_model.is_cached:
                self.whisper_model.download()
            self.whisper_model.load()
            self.audio_client = self.whisper_model.get_audio_client()
            self.audio_client.settings.language = 'en'
            
            print("[SUCCESS] Hardware Locked.")
        except Exception as e:
            print(f"[!] Critical Load Error: {e}")
            raise

    def speak(self, text):
        clean_text = re.sub(r"[^a-zA-Z0-9\s\.\?\!,'\-]", '', text).strip()
        if not clean_text or len(clean_text) < 2: return
        print(f"\n[CODEX]: {clean_text}")
        
        ps_cmd = "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak($env:CODEX_SPEECH_TEXT)"
        
        custom_env = os.environ.copy()
        custom_env["CODEX_SPEECH_TEXT"] = clean_text
        
        subprocess.run([POWERSHELL_EXE, "-Command", ps_cmd], env=custom_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def listen(self, filename=TEMP_WAV_PATH, samplerate=16000, threshold=0.03, silence_delay=2.0):
        chunk_samples = int(samplerate * 0.1)
        max_silence_chunks = int(silence_delay / 0.1)
        audio_buffer, is_recording, silence_counter = [], False, 0
        
        with sd.InputStream(device=self.mic_index, samplerate=samplerate, channels=1, dtype='float32') as stream:
            while True:
                chunk, _ = stream.read(chunk_samples)
                rms = np.sqrt(np.mean(chunk**2))
                if rms > threshold:
                    if not is_recording: is_recording = True
                    audio_buffer.append(chunk)
                    silence_counter = 0 
                elif is_recording:
                    audio_buffer.append(chunk)
                    silence_counter += 1
                    if silence_counter >= max_silence_chunks: break 
                        
        if not audio_buffer: return False
        recording = np.concatenate(audio_buffer, axis=0)
        if len(recording) < samplerate: return False
            
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(np.int16(recording * 32767).tobytes())
        return True

    def push_transcript(self, role, text):
        try: requests.post("http://127.0.0.1:8090/api/collections/transcripts/records", json={"role": role, "text": text}, timeout=0.5)
        except Exception: pass

    def push_to_vault(self, content, record_type="note"):
        try: requests.post("http://127.0.0.1:8090/api/collections/vault/records", json={"content": content, "type": record_type}, timeout=0.1)
        except Exception: pass

    def run(self):
        self.load_hardware()
        print("\n[SYSTEM] Calibrating audio floor. Please remain silent...")
        
        recording = sd.rec(int(2.0 * 16000), samplerate=16000, channels=1, dtype='float32', device=self.mic_index)
        sd.wait()
        vad_threshold = max(np.sqrt(np.mean(recording**2)) * 3.0, 0.05)

        self.speak("System online. Algorithmic Routing active.")
        hallucinations = ["thank you", "watching", "subscribe", "cannot process", "audio file", "i'm sorry", "am sorry", "hear that", "subtitle"]
        
        while True:
            if self.listen(filename=TEMP_WAV_PATH, threshold=vad_threshold):
                try:
                    result = self.audio_client.transcribe(TEMP_WAV_PATH)
                    clean_text = result.text.strip()
                    lower_text = clean_text.lower()
                    
                    if len(clean_text) < 2: continue
                    if any(h in lower_text for h in hallucinations) and len(clean_text) < 60:
                        continue

                    print(f"\n[YOU]: {clean_text}")
                    
                    # Intercept simple operational commands locally to save tokens
                    if lower_text in ["codex shutdown", "codex sleep"]:
                        self.speak("Shutting down. Goodbye, CEO.")
                        self.shutdown()
                        sys.exit(0)

                    if "codex note" in lower_text or "codex remember" in lower_text:
                        content = re.sub(r'codex (note|remember)\s*(that)?', '', lower_text).strip()
                        self.push_to_vault(content)
                        self.speak("Memory secured.")
                        continue

                    # ==========================================
                    # ALGORITHMIC WORKLOAD ROUTER (Math-Based Heuristics)
                    # ==========================================
                    words = clean_text.split()
                    word_count = len(words)
                    digit_count = sum(c.isdigit() for c in clean_text)
                    
                    # Word boundaries prevent false positive matches. Added "search" and "look up"
                    logic_terms = [r"\bif\b", r"\bthen\b", r"\bexcept\b", r"\bassuming\b", r"\bbecause\b", r"\btherefore\b", r"\bcalculate\b", r"\bsolve\b", r"\bdetermine\b", r"\bwhy\b", r"how many", r"\bsearch\b", r"\blook up\b"]
                    logic_count = sum(len(re.findall(term, lower_text)) for term in logic_terms)
                    
                    # The INT4 Mathematical Limits
                    is_too_long = word_count >= 25
                    is_too_factual = digit_count >= 3
                    is_too_logical = logic_count >= 2
                    is_complex_question = "?" in clean_text and word_count > 6
                    is_manual_override = "codex query" in lower_text or "codex, query" in lower_text
                    
                    requires_cloud = is_too_long or is_too_factual or is_too_logical or is_complex_question or is_manual_override

                    # UX Output so you can see exactly why the math routed it
                    print(f"  [ROUTER MATH] Words: {word_count}/25 | Digits: {digit_count}/3 | Logic: {logic_count}/2 | Complex ?: {is_complex_question}")
                    print(f"  [DESTINATION] {'☁️ GEMINI 3 FLASH (with Search)' if requires_cloud else '🖥️ LOCAL QWEN 4B'}")

                    # ==========================================
                    # EXECUTION LAYER
                    # ==========================================
                    current_date = datetime.datetime.now().strftime('%A, %B %d, %Y')
                    
                    if requires_cloud:
                        if not self.gemini_client:
                            self.speak("Cloud keys are missing. I cannot route this task.")
                            continue

                        try:
                            # Search Grounding correctly enabled via official SDK types
                            cloud_response = self.gemini_client.models.generate_content(
                                model='gemini-3-flash-preview',
                                contents=clean_text,
                                config=types.GenerateContentConfig(
                                    system_instruction=f"You are the DSIE Codex Cloud Engine. Today is {current_date}. Provide direct, highly accurate, and conversational answers. Keep formatting simple as your response will be read aloud.",
                                    temperature=0.2,
                                    tools=[types.Tool(google_search=types.GoogleSearch())]
                                )
                            )
                            cloud_reply = cloud_response.text.strip()
                            
                            self.push_transcript("CEO", clean_text)
                            self.push_transcript("Codex (Gemini)", cloud_reply)
                            self.speak(cloud_reply)
                            
                        except Exception as e:
                            print(f"[!] Gemini API Failed: {e}")
                            self.speak("Cloud connection failed. I cannot retrieve that data right now.")
                            
                    else:
                        sys_prompt = f"PRIMARY DIRECTIVE: You are the local voice dispatcher for the DSIE Codex OS. Today is {current_date}. Respond briefly and conversationally."
                        messages = [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": clean_text}
                        ]

                        # Map MCP Tools to MSFL OpenAI Schema
                        available_mcp_tools = get_tools_for_llm()
                        tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}} for t in available_mcp_tools]

                        # Phase 1: Initial Inference with Tooling Enabled
                        response = self.chat_client.complete_chat(messages, tools=tools)
                        
                        # Phase 2: Tool Execution Loop (Interception)
                        if response.choices[0].message.tool_calls:
                            # Append the assistant's tool-call request to the message history
                            # We convert the message object back to a dict for the SDK
                            assistant_msg = {
                                "role": "assistant",
                                "content": response.choices[0].message.content,
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "type": "function",
                                        "function": {
                                            "name": tc.function.name,
                                            "arguments": tc.function.arguments
                                        }
                                    } for tc in response.choices[0].message.tool_calls
                                ]
                            }
                            messages.append(assistant_msg)

                            for tool_call in response.choices[0].message.tool_calls:
                                tool_name = tool_call.function.name
                                tool_args = json.loads(tool_call.function.arguments)
                                
                                print(f"  [MCP EXECUTE] Calling: {tool_name}({tool_call.function.arguments})")
                                tool_result = asyncio.run(call_mcp_tool(tool_name, tool_args))

                                # Append the result as a Tool role message
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": str(tool_result)
                                })

                                # SOP-01: Aggressive Memory Purge before re-inference
                                gc.collect()

                            # Phase 3: Final Synthesis (Second Inference Pass)
                            response = self.chat_client.complete_chat(messages) # No tools on second pass

                        reply = response.choices[0].message.content.strip()
                        
                        self.push_transcript("CEO", clean_text)
                        self.push_transcript("Codex (Local)", reply)
                        self.speak(reply)

                except Exception as e:
                    print(f"[!] Runtime Error: {e}")

    def shutdown(self):
        print("\n[SYSTEM] Releasing NPU & MCP Nexus...")
        if hasattr(self, 'chat_client'): del self.chat_client
        if hasattr(self, 'audio_client'): del self.audio_client
        if self.llm_model: self.llm_model.unload()
        if self.whisper_model: self.whisper_model.unload()
        try:
            asyncio.run(shutdown_nexus())
        except Exception:
            pass

if __name__ == "__main__":
    core = DSIECore()
    try: core.run()
    except KeyboardInterrupt: core.shutdown()