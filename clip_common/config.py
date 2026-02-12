"""Configuration loading for clip-manager."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class Config:
    max_history: int = 500
    hotkey: str = "ctrl+grave"
    db_path: str = ""
    max_image_size: int = 10 * 1024 * 1024  # 10MB

    def __post_init__(self):
        if not self.db_path:
            data_home = os.environ.get(
                "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
            )
            self.db_path = str(Path(data_home) / "clip-manager" / "clips.db")


def _get_config_path() -> Path:
    """Get the config file path, respecting env override."""
    env_path = os.environ.get("CLIP_MANAGER_CONFIG")
    if env_path:
        return Path(env_path)
    config_home = os.environ.get(
        "XDG_CONFIG_HOME", os.path.expanduser("~/.config")
    )
    return Path(config_home) / "clip-manager" / "config.toml"


def load_config() -> Config:
    """Load configuration from TOML file, falling back to defaults."""
    config_path = _get_config_path()
    config = Config()

    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            if "max_history" in data:
                config.max_history = int(data["max_history"])
            if "hotkey" in data:
                config.hotkey = str(data["hotkey"])
            if "db_path" in data:
                config.db_path = os.path.expanduser(str(data["db_path"]))
            if "max_image_size" in data:
                config.max_image_size = int(data["max_image_size"])
            logger.info("Loaded config from %s", config_path)
        except Exception:
            logger.exception("Failed to load config from %s, using defaults", config_path)

    return config
