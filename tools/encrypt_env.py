import os
from pathlib import Path
import win32crypt

def encrypt_env_file():
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / '.env'
    encrypted_path = base_dir / '.env.encrypted'

    if not env_path.exists():
        print("No .env file found to encrypt.")
        return

    with open(env_path, 'r', encoding='utf-8') as f:
        env_data = f.read().encode('utf-8')

    entropy = b""
    description = "DSIE Codex Env Variables"
    
    # Encrypt using DPAPI
    encrypted_data = win32crypt.CryptProtectData(env_data, description, entropy, None, None, 0)

    with open(encrypted_path, 'wb') as f:
        f.write(encrypted_data)

    print(f"Successfully encrypted .env to {encrypted_path}")

if __name__ == "__main__":
    encrypt_env_file()
