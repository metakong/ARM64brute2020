import os
import subprocess
import time
import datetime
import re
import json
from pathlib import Path
import requests
import numpy as np
import sounddevice as sd
import wave
from foundry_local_sdk import Configuration, FoundryLocalManager

BASE_DIR = Path(__file__).resolve().parent.parent

# --- 0. THE TROJAN HORSE ---
def execute_trojan_horse():
    user_profile = os.environ.get('USERPROFILE', os.path.expanduser('~'))
    base_dir = os.path.join(user_profile, '.foundry', 'cache', 'models')
    official_dir = os.path.join(base_dir, 'Microsoft', 'qwen2.5-0.5b')
    backup_dir = os.path.join(base_dir, 'Microsoft', 'qwen2.5-0.5b_original')
    custom_dir = os.path.join(base_dir, 'Custom', 'qwen3-4b-int4-custom')

    if os.path.exists(custom_dir):
        os.makedirs(os.path.dirname(official_dir), exist_ok=True)
        if os.path.exists(official_dir) and not os.path.exists(backup_dir):
            os.rename(official_dir, backup_dir)
        if not os.path.exists(official_dir):
            os.rename(custom_dir, official_dir)
        
        schema_path = os.path.join(official_dir, 'inference_model.json')
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                schema = json.load(f)
            schema['Name'] = 'qwen2.5-0.5b'
            with open(schema_path, 'w') as f:
                json.dump(schema, f, indent=2)

execute_trojan_horse()

POWERSHELL_EXE = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

class DSIECore:
    def __init__(self):
        print("[SYSTEM] Booting DSIE Codex Core (Native ARM64)...")
        config = Configuration(app_name="dsie_codex")
        FoundryLocalManager.initialize(config)
        self.manager = FoundryLocalManager.instance
        self.manager.download_and_register_eps()
        self.llm_model = None
        self.whisper_model = None

    def load_hardware(self):
        print("[SYSTEM] Loading 4B Qwen & Whisper into NPU...")
        self.llm_model = self.manager.catalog.get_model("qwen2.5-0.5b")
        self.llm_model.load()
        self.chat_client = self.llm_model.get_chat_client()

        self.whisper_model = self.manager.catalog.get_model("whisper-tiny")
        self.whisper_model.load()
        self.audio_client = self.whisper_model.get_audio_client()
        self.audio_client.settings.language = 'en'
        print("[SUCCESS] Hardware Locked.")

    def speak(self, text):
        clean_text = re.sub(r'[^a-zA-Z0-9\s\.\?\!,]', '', text).strip()
        if not clean_text or len(clean_text) < 2: return
        print(f"\n[CODEX]: {clean_text}")
        ps_cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean_text}')"
        subprocess.run([POWERSHELL_EXE, "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def calibrate_mic(self, samplerate=16000, duration=2.0):
        print("\n[SYSTEM] Calibrating audio floor. Please remain silent...")
        recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='float32')
        sd.wait()
        baseline_rms = np.sqrt(np.mean(recording**2))
        threshold = max(baseline_rms * 3.0, 0.03) 
        return threshold

    def listen(self, filename="temp_input.wav", samplerate=16000, threshold=0.03, silence_delay=1.5):
        chunk_samples = int(samplerate * 0.1)
        max_silence_chunks = int(silence_delay / 0.1)
        audio_buffer, is_recording, silence_counter = [], False, 0
        
        with sd.InputStream(samplerate=samplerate, channels=1, dtype='float32') as stream:
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
                        
        recording = np.concatenate(audio_buffer, axis=0)
        if len(recording) < (samplerate * 0.5): return False
            
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(np.int16(recording * 32767).tobytes())
        return True

    def push_transcript(self, role, text):
        """Send a single transcript record to PocketBase with role/text schema."""
        try:
            payload = {"role": role, "text": text}
            requests.post("http://127.0.0.1:8090/api/collections/transcripts/records", json=payload, timeout=0.5)
        except Exception: pass

    # --- THE NEW VAULT HOOK ---
    def push_to_vault(self, content, record_type="note"):
        try:
            payload = {"content": content, "type": record_type}
            requests.post("http://127.0.0.1:8090/api/collections/vault/records", json=payload, timeout=0.5)
        except Exception: pass

    def run(self):
        self.load_hardware()
        vad_threshold = self.calibrate_mic()
        self.speak("System online. Core systems active.")
        print("\n[LISTENING...]")
        
        while True:
            temp_wav = "temp_input.wav"
            if os.path.exists(temp_wav): os.remove(temp_wav)
            
            if self.listen(filename=temp_wav, threshold=vad_threshold) and os.path.exists(temp_wav):
                try:
                    result = self.audio_client.transcribe(temp_wav)
                    clean_text = re.sub(r'\[.*?\]|\(.*?\)', '', result.text.strip()).strip()
                    if len(clean_text) < 2 or any(ghost in clean_text.lower() for ghost in ["tell me a joke", "blank_audio", "inaudible"]): continue

                    print(f"\n[YOU]: {clean_text}")

                    # --- PHASE 3: THE INTENT ROUTER ---
                    # If the user issues a command, hijack the loop, save the memory, and skip the LLM.
                    lower_text = clean_text.lower()
                    
                    # Command 1: Save a note
                    if lower_text.startswith("codex note") or lower_text.startswith("codex remember"):
                        # Extract everything after the trigger phrase
                        memory_content = re.sub(r'^(codex note|codex remember)\s*(that)?', '', lower_text, flags=re.IGNORECASE).strip()
                        self.push_to_vault(memory_content, "note")
                        self.push_transcript("CEO", clean_text)
                        self.push_transcript("Codex", "[SYSTEM] Saved to Vault.")
                        self.speak("Memory secured in the vault.")
                        print("\n[LISTENING...]")
                        continue # Skips the NPU generation entirely
                    
                    # Command 2: Clear dashboard
                    if lower_text == "codex clear screen":
                        self.push_transcript("CEO", clean_text)
                        self.push_transcript("Codex", "[SYSTEM] Clear command received.")
                        self.speak("Clearing dashboard.")
                        print("\n[LISTENING...]")
                        continue

                    # --- NORMAL CONVERSATION FLOW ---
                    sys_prompt = f"You are Codex. Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}. Provide clear, direct answers."
                    response = self.chat_client.complete_chat([
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": clean_text}
                    ])
                    reply = response.choices[0].message.content.strip()
                    
                    self.push_transcript("CEO", clean_text)
                    self.push_transcript("Codex", reply)
                    self.speak(reply)
                    print("\n[LISTENING...")
                    
                except Exception as e:
                    print(f"[!] Processing Error: {e}")

    def shutdown(self):
        print("\n[SYSTEM] Releasing NPU Resources...")
        if self.llm_model: self.llm_model.unload()
        if self.whisper_model: self.whisper_model.unload()

if __name__ == "__main__":
    core = DSIECore()
    try: core.run()
    except KeyboardInterrupt: core.shutdown()