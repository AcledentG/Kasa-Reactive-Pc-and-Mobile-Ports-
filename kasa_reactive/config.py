"""
config.py
=========

Loads and saves user settings to JSON in a platform-appropriate location.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import List

from .bulb_control import BulbEntry


CONFIG_FILENAME = "kasa_reactive_config.json"


def _user_data_dir() -> str:
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None and getattr(app, "user_data_dir", None):
            return app.user_data_dir
    except Exception:
        pass
    if hasattr(sys, "frozen"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _config_path() -> str:
    d = _user_data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, CONFIG_FILENAME)


@dataclass
class AppConfig:
    bulbs: List[BulbEntry] = field(default_factory=list)
    audio_device: str = ""
    update_hz: float = 20.0
    haptics_on_beat: bool = True
    keep_screen_on: bool = True
    use_amoled_black: bool = True


def load_config() -> AppConfig:
    path = _config_path()
    if not os.path.exists(path):
        return AppConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = AppConfig()
        if "bulbs" in data:
            cfg.bulbs = [BulbEntry(**b) for b in data["bulbs"]]
        for key in ("audio_device", "update_hz",
                    "haptics_on_beat", "keep_screen_on", "use_amoled_black"):
            if key in data:
                setattr(cfg, key, data[key])
        return cfg
    except Exception as e:
        print(f"[config] failed to load: {e}", flush=True)
        return AppConfig()


def save_config(cfg: AppConfig) -> bool:
    path = _config_path()
    try:
        bulbs_clean = [asdict(b) for b in cfg.bulbs]
        out = asdict(cfg)
        out["bulbs"] = bulbs_clean
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        return True
    except Exception as e:
        print(f"[config] save failed: {e}", flush=True)
        return False
