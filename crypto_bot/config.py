import os
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return config

def get_config() -> dict:
    cfg = load_config()
    # Override from environment
    cfg["exchange"]["api_key"] = os.getenv("OKX_API_KEY", "")
    cfg["exchange"]["secret"] = os.getenv("OKX_SECRET", "")
    cfg["exchange"]["password"] = os.getenv("OKX_PASSWORD", "")
    cfg["notify"]["telegram"]["token"] = os.getenv("TG_BOT_TOKEN", cfg["notify"]["telegram"]["token"])
    cfg["notify"]["telegram"]["chat_id"] = os.getenv("TG_CHAT_ID", cfg["notify"]["telegram"]["chat_id"])
    return cfg
