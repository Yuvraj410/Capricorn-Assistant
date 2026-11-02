"""Settings loading: repo defaults deep-merged with the user's copy in the user data folder."""
from __future__ import annotations

import copy
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from . import paths

log = logging.getLogger(__name__)

DATA_README = """capricorn-data - everything Capricorn installed or saved on this PC
=================================================================
python\\        Python environment + packages (made by Setup.exe)
models\\        wake-word (Vosk) and speech-to-text (Whisper) models
logs\\          capricorn.log = what Capri heard; actions.log = everything she opened
voice_cache\\   pre-recorded Capri lines (tools\\split_voice_lines.py)
settings.yaml    your settings (wake words, models, size/position, hotkey, voice...)
permissions.yaml what Capri may open (apps, folders, files, websites, media, system)
approvals.json   things you already said "yes" to - Capri won't ask again (delete to reset)

This folder is personal: it is git-ignored and never uploaded.
Edit the .yaml files, then tray icon > "Reload settings & permissions".
Delete this folder to reset Capricorn (run Setup.exe again afterwards).
"""


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_yaml(p: Path) -> dict:
    try:
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as e:
        log.error("Could not parse %s: %s (using defaults)", p, e)
        return {}


def ensure_user_files(profile: str | None = None) -> None:
    """Create the user's settings/permissions on first run.

    profile: "safe" or "full" - only used when permissions.yaml doesn't exist yet,
    or when explicitly re-applied with `python -m capricorn --profile full`.
    """
    ud = paths.user_dir()
    note = ud / "README.txt"
    if not note.exists():
        note.write_text(DATA_README, encoding="utf-8")
    s = ud / paths.SETTINGS_FILE
    if not s.exists():
        shutil.copyfile(paths.DEFAULTS_DIR / "settings.yaml", s)
        log.info("Created %s", s)
    p = ud / paths.PERMISSIONS_FILE
    if profile or not p.exists():
        src = paths.DEFAULTS_DIR / f"permissions.{profile or 'safe'}.yaml"
        if p.exists():
            shutil.copyfile(p, p.with_suffix(".yaml.bak"))
        shutil.copyfile(src, p)
        log.info("Wrote %s from %s", p, src.name)


class Settings:
    """Dot-path access: settings.get("ui.scale")."""

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        defaults = _read_yaml(paths.DEFAULTS_DIR / "settings.yaml")
        user = _read_yaml(paths.user_dir() / paths.SETTINGS_FILE)
        self.data: dict = _deep_merge(defaults, user)

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def save_many(self, values: dict[str, Any]) -> None:
        """Write several dotted keys to the user file in one go."""
        up = paths.user_dir() / paths.SETTINGS_FILE
        user = _read_yaml(up)
        for dotted, value in values.items():
            cur = user
            parts = dotted.split(".")
            for part in parts[:-1]:
                nxt = cur.get(part)
                if not isinstance(nxt, dict):
                    nxt = cur[part] = {}
                cur = nxt
            cur[parts[-1]] = value
        with open(up, "w", encoding="utf-8") as f:
            yaml.safe_dump(user, f, sort_keys=False, allow_unicode=True)
        self.reload()

    def set_and_save(self, dotted: str, value: Any) -> None:
        """Update one value in the *user* file (keeps the user's other edits and comments-free)."""
        up = paths.user_dir() / paths.SETTINGS_FILE
        user = _read_yaml(up)
        cur = user
        parts = dotted.split(".")
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value
        # Rewriting loses comments; keep a pristine copy of the documented defaults next to it.
        doc = paths.user_dir() / "settings.defaults.yaml"
        if not doc.exists():
            shutil.copyfile(paths.DEFAULTS_DIR / "settings.yaml", doc)
        with open(up, "w", encoding="utf-8") as f:
            yaml.safe_dump(user, f, sort_keys=False, allow_unicode=True)
        self.reload()
