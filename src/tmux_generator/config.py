from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


DEFAULT_CONFIG_PATH = Path.home() / ".tmux-generator" / "config.json"
DEFAULT_UI_CONFIG_PATH = Path.cwd() / ".codex" / "tmux-generator-ui.json"


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 6060


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> ServerConfig:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        return ServerConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return ServerConfig(host=str(data.get("host", "0.0.0.0")), port=int(data.get("port", 6060)))


def load_ui_config(path: Path | str = DEFAULT_UI_CONFIG_PATH) -> dict:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def save_ui_config(data: dict, path: Path | str = DEFAULT_UI_CONFIG_PATH) -> dict:
    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
