"""Where things live.

* Repo files (code, assets, default configs) are read-only at runtime.
* Everything installed or personal (Python environment, models, settings, permissions,
  logs, voice cache) lives in ONE visible folder next to the code:
      <install folder>/capricorn-data/
  It is git-ignored, so the repo never contains personal data.
  If that folder isn't writable, %APPDATA%\\Capricorn is used instead.
  Override with the CAPRICORN_HOME environment variable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
ASSETS_DIR = REPO_DIR / "assets"
CHARACTER_DIR = ASSETS_DIR / "character"
FONTS_DIR = ASSETS_DIR / "fonts"
DEFAULTS_DIR = PACKAGE_DIR / "defaults"


DATA_DIR_NAME = "capricorn-data"
LEGACY_DATA_DIR_NAME = "capricon-data"     # the project used to be called "Capricon"
_user_dir_cache: Path | None = None


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def user_dir() -> Path:
    global _user_dir_cache
    env = os.environ.get("CAPRICORN_HOME")
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if _user_dir_cache is not None:
        return _user_dir_cache
    p = REPO_DIR / DATA_DIR_NAME
    legacy = REPO_DIR / LEGACY_DATA_DIR_NAME
    if not p.exists() and legacy.is_dir():    # not migrated yet (scripts\migrate_name.ps1 does that)
        p = legacy
    if not _writable(p):
        if sys.platform == "win32":
            p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Capricorn"
        else:
            p = Path.home() / ".config" / "capricorn"
        p.mkdir(parents=True, exist_ok=True)
    _user_dir_cache = p
    return p


def models_dir() -> Path:
    p = user_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = user_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def voice_cache_dir() -> Path:
    p = user_dir() / "voice_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def voices_dir() -> Path:
    """Reference recordings for Capri's own voice (capri.wav). Personal - never in the repo."""
    p = user_dir() / "voices"
    p.mkdir(parents=True, exist_ok=True)
    return p


def voice_env_dir() -> Path:
    """Separate Python environment for the optional voice model (PyTorch + Chatterbox)."""
    return user_dir() / "voice-env"


def voice_python() -> Path:
    d = voice_env_dir()
    return d / "Scripts" / "python.exe" if sys.platform == "win32" else d / "bin" / "python"


SETTINGS_FILE = "settings.yaml"
PERMISSIONS_FILE = "permissions.yaml"
