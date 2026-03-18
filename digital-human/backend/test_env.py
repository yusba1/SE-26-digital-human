import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path('.env')
print(f"Env file exists: {env_path.exists()}")
if env_path.exists():
    load_dotenv(env_path)
    print(f"ALIBABA_CLOUD_ACCESS_KEY_ID: {os.getenv('ALIBABA_CLOUD_ACCESS_KEY_ID', 'NOT_FOUND')[:15]}...")
    print(f"ALIBABA_CLOUD_ACCESS_KEY_SECRET: {os.getenv('ALIBABA_CLOUD_ACCESS_KEY_SECRET', 'NOT_FOUND')[:15]}...")
    print(f"TINGWU_ENDPOINT: {os.getenv('TINGWU_ENDPOINT', 'NOT_FOUND')}")
    print(f"TINGWU_APP_KEY: {os.getenv('TINGWU_APP_KEY', 'NOT_FOUND')[:15]}...")
