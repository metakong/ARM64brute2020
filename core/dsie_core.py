import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
from tools.intent_logger import log_intent

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
        
        load_dotenv(str(BASE_DIR / 'secrets' / '.env'))
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        if self.google_api_key:
            self.gemini_client = genai.Client(api_key=self.google_api_key)
        else:
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
        
        asyncio.run(initialize_nexus())

    def load_hardware(self):
        try:
            self.llm_model = self.manager.catalog.get_model("qwen2.5-0.5b")
            self.llm_model.load()
            self.chat_client = self.llm_model.get_chat_client()

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

    def process_text(self, clean_text):
        """Processes text through the NPU inference engine."""
        lower_text = clean_text.lower()
        words = clean_text.split()
        current_date = datetime.datetime.now().strftime('%A, %B %d, %Y')

        if lower_text in ["codex shutdown", "codex sleep"]:
            self.speak("Shutting down. Goodbye, CEO.")
            self.shutdown()
            sys.exit(0)

        if "codex note" in lower_text or "codex remember" in lower_text:
            content = re.sub(r'codex (note|remember)\s*(that)?', '', lower_text).strip()
            self.push_to_vault(content)
            self.speak("Memory secured.")
            return "Memory secured."

        # ==========================================
        # VANGUARD ROUTER LOGIC
        # ==========================================
        routing_decision = "Local"
        first_10_words = " ".join(words[:10]).lower()
        triggers = ["cloud", "gemini", "complex", "analyze", "code", "search", "database", "web", "internet", "osint", "news", "current", "email", "gmail", "inbox", "reply", "send", "message", "communications"]
        force_cloud = any(t in first_10_words for t in triggers)
        
        log_intent(clean_text, routing_decision if not force_cloud else "Cloud")

        capability_schema = f"""
        DOMAIN: Edge Routing / Status Notification.
        CONSTRAINTS: 4B Parameter limit. No local file access.
        GOAL: Analyze intent. Today is {current_date}. 
        
        SOP-04 (Context Hydration): If the user's prompt implies "working theory", "SOP", "rules", or "business logic", 
        you MUST execute fetch_business_sop to retrieve the local context. 
        Once retrieved, you MUST include that context in your payload when triggering delegate_to_gemini.

        SOP-05 (Asynchronous Handoff): If the user's prompt requests a deep research report, a long-running scrape, or contains "Background", 
        you MUST immediately acknowledge the handoff by speaking: "[SOP-Active] Dispatching task to the background queue."

        SOP-06 (OSINT Chaining): If the user's prompt requests current data, news, or explicitly asks to "search the web", 
        you MUST first call osint_scrape to gather raw internet data. 
        Once the data is retrieved, you MUST package that raw data into the payload for delegate_to_gemini and dispatch it to the background queue.

        SOP-07 (Comms Chaining): If the user asks to check email or read the inbox, you MUST use fetch_unread_emails, 
        then package the retrieved text into delegate_to_gemini for summarization. 
        If the user asks to reply or send an email, you MUST package the request into delegate_to_gemini to draft the professional response, 
        and then use send_email to dispatch the resulting draft.
        
        If the user request is complex or matches your trigger list, use the delegate_to_gemini tool.
        """
        
        messages = [
            {"role": "system", "content": capability_schema},
            {"role": "user", "content": clean_text}
        ]

        available_mcp_tools = get_tools_for_llm()
        tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}} for t in available_mcp_tools]
        tool_choice = {"type": "function", "function": {"name": "delegate_to_gemini"}} if force_cloud else "auto"

        response = self.chat_client.complete_chat(messages, tools=tools, tool_choice=tool_choice)
        
        prefix = "[SOP-Active]"
        if response.choices[0].message.tool_calls:
            tool_names = [tc.function.name for tc in response.choices[0].message.tool_calls]
            self.speak(f"[SOP-Active] -> Routing to {', '.join(tool_names)}")

            assistant_msg = {
                "role": "assistant",
                "content": response.choices[0].message.content,
                "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in response.choices[0].message.tool_calls]
            }
            messages.append(assistant_msg)

            for tool_call in response.choices[0].message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                print(f"  [MCP EXECUTE] Calling: {tool_name}")
                tool_result = asyncio.run(call_mcp_tool(tool_name, tool_args))

                if tool_name == "delegate_to_gemini": prefix = "[Vanguard-Result]"
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(tool_result)})
                gc.collect()

            response = self.chat_client.complete_chat(messages)
        else:
            prefix = "[Local-FreeStyle]"

        reply = f"{prefix} {response.choices[0].message.content.strip()}"
        self.push_transcript("CEO", clean_text)
        self.push_transcript("Codex", reply)
        self.speak(reply)
        return reply

    def run(self):
        self.load_hardware()
        print("\n[SYSTEM] Calibrating audio floor...")
        recording = sd.rec(int(1.5 * 16000), samplerate=16000, channels=1, dtype='float32', device=self.mic_index)
        sd.wait()
        vad_threshold = max(np.sqrt(np.mean(recording**2)) * 3.0, 0.05)
        self.speak("System online. Algorithmic Routing active.")
        hallucinations = ["thank you", "watching", "subscribe", "cannot process", "audio file", "i'm sorry", "am sorry", "hear that", "subtitle"]
        
        while True:
            if self.listen(filename=TEMP_WAV_PATH, threshold=vad_threshold):
                try:
                    result = self.audio_client.transcribe(TEMP_WAV_PATH)
                    clean_text = result.text.strip()
                    if len(clean_text) < 2: continue
                    if any(h in clean_text.lower() for h in hallucinations) and len(clean_text) < 60: continue
                    print(f"\n[YOU]: {clean_text}")
                    self.process_text(clean_text)
                except Exception as e: print(f"[!] Runtime Error: {e}")

    def shutdown(self):
        print("\n[SYSTEM] Releasing Hardware...")
        if hasattr(self, 'chat_client'): del self.chat_client
        if hasattr(self, 'audio_client'): del self.audio_client
        if self.llm_model: self.llm_model.unload()
        if self.whisper_model: self.whisper_model.unload()
        try: asyncio.run(shutdown_nexus())
        except Exception: pass

if __name__ == "__main__":
    core = DSIECore()
    try: core.run()
    except KeyboardInterrupt: core.shutdown()