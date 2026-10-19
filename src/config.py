"""
Garmin AI Coach - Core Configuration Manager
"""
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TOKENS_DIR = DATA_DIR / "tokens"
CONFIG_DIR = BASE_DIR / "config"
DB_PATH = DATA_DIR / "garmin_coach.db"

# Ensure data directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
TOKENS_DIR.mkdir(parents=True, exist_ok=True)

# Environment settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "30"))
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")


def load_users_config() -> List[Dict[str, Any]]:
    """Loads athletes from config/users.yaml or falls back to template/env."""
    users_file = CONFIG_DIR / "users.yaml"
    users_example = CONFIG_DIR / "users.yaml.example"

    if users_file.exists():
        with open(users_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("users", [])
    elif users_example.exists():
        # Fallback to example for schema/structure verification
        with open(users_example, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data.get("users", [])
    return []


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a specific athlete configuration by ID."""
    users = load_users_config()
    for u in users:
        if u.get("id") == user_id:
            return u
    return None
