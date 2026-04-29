import os

# 1. Map Cache
os.environ["FOUNDRY_LOCAL_CACHE_DIR"] = r"Z:\foundry_cache"

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

import subprocess
import time
import datetime
import re
import json
from pathlib import Path
import requests
import numpy as np
import wave
import sounddevice as sd

from foundry_local_sdk import Configuration, FoundryLocalManager
from foundry_local_sdk.logging_helper import LogLevel

POWERSHELL_EXE = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

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
        
        # 3. FORCE THE EXECUTION PROVIDER GLOBALLY
        # We use additional_settings to bypass the catalog and force the C# core
        # to initialize ONNX with the Qualcomm Neural Network Execution Provider.
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

    def load_hardware(self):
        print("[SYSTEM] Syncing Models with Native SDK Registry...")
        try:
            # 4. Request the generic model so Azure doesn't block it,
            # but it will be executed on the NPU because of the global config override above.
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
        clean_text = re.sub(r'[^a-zA-Z0-9\s\.\?\!,]', '', text).strip()
        if not clean_text or len(clean_text) < 2: return
        print(f"\n[CODEX]: {clean_text}")
        ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean_text}')"
        subprocess.run([POWERSHELL_EXE, "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def listen(self, filename="temp_input.wav", samplerate=16000, threshold=0.03, silence_delay=0.5):
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
        try: requests.post("http://127.0.0.1:8090/api/collections/transcripts/records", json={"role": role, "text": text}, timeout=0.1)
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

        self.speak("System online. Core systems active.")
        hallucinations = ["thank you", "watching", "subscribe", "cannot process", "audio file", "i'm sorry", "am sorry", "hear that", "subtitle"]
        
        while True:
            temp_wav = "temp_input.wav"
            if self.listen(filename=temp_wav, threshold=vad_threshold):
                try:
                    result = self.audio_client.transcribe(temp_wav)
                    clean_text = result.text.strip()
                    lower_text = clean_text.lower()
                    
                    if len(clean_text) < 2: continue
                    if any(h in lower_text for h in hallucinations) and len(clean_text) < 60:
                        print(f"--- [AUDIO] Ignored Whisper Hallucination: '{clean_text}'")
                        continue

                    print(f"\n[YOU]: {clean_text}")
                    
                    if "codex note" in lower_text or "codex remember" in lower_text:
                        content = re.sub(r'codex (note|remember)\s*(that)?', '', lower_text).strip()
                        self.push_to_vault(content)
                        self.speak("Memory secured.")
                        continue

                    response = self.chat_client.complete_chat([
                        {"role": "system", "content": f"You are Codex. Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}. Direct answers only."},
                        {"role": "user", "content": clean_text}
                    ])
                    reply = response.choices[0].message.content
                    self.push_transcript("CEO", clean_text)
                    self.push_transcript("Codex", reply)
                    self.speak(reply)
                except Exception as e:
                    print(f"[!] Runtime Error: {e}")

    def shutdown(self):
        print("\n[SYSTEM] Releasing NPU...")
        if hasattr(self, 'chat_client'): del self.chat_client
        if hasattr(self, 'audio_client'): del self.audio_client
        if self.llm_model: self.llm_model.unload()
        if self.whisper_model: self.whisper_model.unload()

if __name__ == "__main__":
    core = DSIECore()
    try: core.run()
    except KeyboardInterrupt: core.shutdown()