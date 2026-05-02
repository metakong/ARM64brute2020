import os
import json
import time
import random
import atexit
from pathlib import Path

from googleapiclient.errors import HttpError
from google.genai import errors as genai_errors
import requests

try:
    import win32crypt
except ImportError:
    win32crypt = None
from dotenv import load_dotenv

GEMINI_MODEL = "gemini-3-flash-preview"

def clean_json_response(raw_text):
    """
    DEPRECATED: Native structured outputs are now enforced via API schema (May 2026).
    This function remains as a pass-through to avoid breaking legacy imports.
    """
    return raw_text.strip()

def execute_with_backoff(func, *args, max_retries=5, base_delay=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            is_rate_limit = False
            
            if isinstance(e, HttpError):
                if e.resp.status in [403, 429, 500, 503]:
                    is_rate_limit = True
            elif isinstance(e, genai_errors.APIError):
                if e.code in [429, 503]:
                    is_rate_limit = True
            elif isinstance(e, requests.exceptions.HTTPError):
                if e.response is not None and e.response.status_code in [429, 503]:
                    is_rate_limit = True
                elif e.response is not None and e.response.status_code in [403, 404, 451]:
                    # Fail fast for permanent blocks
                    return None
            elif "429" in str(e) or "503" in str(e) or "quota" in str(e).lower():
                is_rate_limit = True

            if attempt == max_retries - 1:
                print(f"     [FATAL] Max retries reached: {e}")
                return None
                
            if is_rate_limit or isinstance(e, json.decoder.JSONDecodeError):
                jitter = random.uniform(0, 1)
                delay = (base_delay * (2 ** attempt)) + jitter
                print(f"     [API THROTTLE] Waiting {delay:.2f}s before retry (Attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
            else:
                raise e

_log_buffer = {}

def flush_logs():
    for log_file_path, lines in _log_buffer.items():
        if not lines:
            continue
        try:
            if os.path.exists(log_file_path):
                if os.path.getsize(log_file_path) > 50 * 1024 * 1024:
                    os.rename(log_file_path, log_file_path + ".bak")
            with open(log_file_path, 'a', encoding='utf-8') as f:
                f.write("".join(lines))
        except Exception:
            pass
        _log_buffer[log_file_path] = []

atexit.register(flush_logs)

def log_action(message, log_file_path):
    print(message)
    if log_file_path not in _log_buffer:
        _log_buffer[log_file_path] = []
        
    formatted_msg = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n"
    _log_buffer[log_file_path].append(formatted_msg)
    
    if len(_log_buffer[log_file_path]) >= 50:
        flush_logs()

def decrypt_env(encrypted_env_path):
    if not win32crypt:
        return False
    try:
        with open(encrypted_env_path, 'rb') as f:
            encrypted_data = f.read()
        entropy = b""
        _, decrypted_data = win32crypt.CryptUnprotectData(encrypted_data, None, entropy, None, None, 0)
        from io import StringIO
        load_dotenv(stream=StringIO(decrypted_data.decode('utf-8')))
        return True
    except Exception as e:
        print(f"Failed to decrypt env: {e}")
        return False
