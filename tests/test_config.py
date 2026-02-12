"""Unit tests for configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from clip_common.config import Config, load_config


class TestConfigDefaults:
    def test_default_values(self):
        config = Config()
        assert config.max_history == 500
        assert config.hotkey == "ctrl+grave"
        assert config.max_image_size == 10 * 1024 * 1024

    def test_default_db_path(self):
        config = Config()
        assert "clip-manager/clips.db" in config.db_path


class TestConfigLoading:
    def test_load_from_toml(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('max_history = 100\nhotkey = "ctrl+shift+v"\n')

        os.environ["CLIP_MANAGER_CONFIG"] = str(config_file)
        try:
            config = load_config()
            assert config.max_history == 100
            assert config.hotkey == "ctrl+shift+v"
        finally:
            del os.environ["CLIP_MANAGER_CONFIG"]

    def test_missing_config_uses_defaults(self, tmp_path):
        os.environ["CLIP_MANAGER_CONFIG"] = str(tmp_path / "nonexistent.toml")
        try:
            config = load_config()
            assert config.max_history == 500
        finally:
            del os.environ["CLIP_MANAGER_CONFIG"]

    def test_partial_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("max_history = 200\n")

        os.environ["CLIP_MANAGER_CONFIG"] = str(config_file)
        try:
            config = load_config()
            assert config.max_history == 200
            assert config.hotkey == "ctrl+grave"  # default preserved
        finally:
            del os.environ["CLIP_MANAGER_CONFIG"]
