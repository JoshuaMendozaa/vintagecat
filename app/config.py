import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    data_dir: Path
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3-vl:8b"
    compsapi_key: str = ""
    monthly_search_limit: int = 80


def get_settings():
    path = ROOT / "config.local.toml"
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    return Settings(
        data_dir=Path(os.getenv("VINTAGECAT_DATA_DIR", str(ROOT / "data"))),
        ollama_url=os.getenv("OLLAMA_URL", config.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/"),
        model=os.getenv("OLLAMA_MODEL", config.get("model", "qwen3-vl:8b")),
        compsapi_key=os.getenv("COMPSAPI_KEY", config.get("compsapi_key", "")),
        monthly_search_limit=max(0, int(config.get("monthly_search_limit", 80))),
    )

