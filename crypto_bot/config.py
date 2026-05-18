import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config(path: Path = CONFIG_PATH) -> dict:
    try:
        with open(path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found at {path}. Copy config.yaml.example if starting fresh.")
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config file {path}: {e}")
    return config

def get_config() -> dict:
    cfg = load_config()
    ex = cfg.setdefault("exchange", {})
    ex["api_key"] = os.getenv("OKX_API_KEY", ex.get("api_key", ""))
    ex["secret"] = os.getenv("OKX_SECRET", ex.get("secret", ""))
    ex["password"] = os.getenv("OKX_PASSWORD", ex.get("password", ""))
    tg = cfg.setdefault("notify", {}).setdefault("telegram", {})
    tg["token"] = os.getenv("TG_BOT_TOKEN", tg.get("token", ""))
    tg["chat_id"] = os.getenv("TG_CHAT_ID", tg.get("chat_id", ""))
    return cfg
