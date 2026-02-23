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

    if not config_path.exists():
        return config

    # Reject symlinks — a symlink here could redirect to arbitrary files.
    if config_path.is_symlink():
        logger.error("Config file is a symlink, ignoring: %s", config_path)
        return config

    # Reject files not owned by the current user.
    stat = config_path.stat()
    if stat.st_uid != os.getuid():
        logger.error("Config file not owned by current user, ignoring: %s", config_path)
        return config

    # Warn on world-readable config (may reveal db_path or other settings).
    if stat.st_mode & 0o077:
        logger.warning(
            "Config file has permissive mode %o, recommend 0600: %s",
            stat.st_mode & 0o777, config_path,
        )

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        if "max_history" in data:
            # Clamp to a sane range — 0 would disable pruning, very large values waste disk.
            config.max_history = max(10, min(int(data["max_history"]), 10_000))

        if "hotkey" in data:
            config.hotkey = str(data["hotkey"])

        if "db_path" in data:
            db_path = Path(os.path.expanduser(str(data["db_path"])))
            allowed_parent = Path.home() / ".local" / "share" / "clip-manager"
            if db_path.parent == allowed_parent:
                config.db_path = str(db_path)
            else:
                logger.error(
                    "db_path must be directly under %s, ignoring: %s",
                    allowed_parent, db_path,
                )

        if "max_image_size" in data:
            config.max_image_size = max(1024, min(int(data["max_image_size"]), 100 * 1024 * 1024))

        logger.info("Loaded config from %s", config_path)
    except Exception:
        logger.exception("Failed to load config from %s, using defaults", config_path)

    return config
