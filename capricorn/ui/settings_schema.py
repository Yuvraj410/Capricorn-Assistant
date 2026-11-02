"""Turns defaults/settings.yaml (values + comments) into a list of editable fields for the settings
screen, so every setting shows up automatically with its comment as help text."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from .. import paths

SECTION_TITLES = {
    "wake": "Wake word & listening", "stt": "Speech recognition", "brain": "Brain (AI model)",
    "personality": "Personality", "conversation": "Conversation", "ui": "Look & screen", "voice": "Voice", "games": "Games",
    "web": "Web", "confirmations": "Confirmations", "music": "Music", "shortcuts": "Shortcuts",
    "sounds": "Sounds",
}
# Better widgets than the type alone would give.
SPECIAL: dict[str, dict] = {
    "personality.slang": {"levels": ["None", "Light", "Regular", "Heavy"]},
    "personality.genz_slang": {"levels": ["Off", "Rare", "Sometimes"]},
    "personality.sass": {"levels": ["Just helpful", "Light wit", "Playful roasting", "Maximum sass"]},
    "personality.reply_length": {"choices": ["short", "medium"]},
    "voice.engine": {"choices": ["auto", "capri", "sapi", "none"]},
    "voice.device": {"choices": ["auto", "cuda", "cpu"]},
    "voice.volume": {"range": (0.1, 3.0, 0.1)},
    "voice.loudness": {"range": (-30, -8, 1)},
    "voice.temperature": {"range": (0.3, 1.2, 0.05)},
    "voice.duck_level": {"range": (0.0, 1.0, 0.05)},
    "voice.seed": {"range": (-1, 99999, 1)},
    "wake.min_confidence": {"range": (0.2, 0.99, 0.05)},
    "wake.command_timeout": {"range": (2.0, 20.0, 0.5)},
    "wake.end_silence": {"range": (0.6, 4.0, 0.1)},
    "conversation.follow_up_seconds": {"range": (2.0, 20.0, 0.5)},
    "conversation.answer_seconds": {"range": (3.0, 30.0, 0.5)},
    "stt.model": {"choices": ["tiny.en", "base.en", "small.en", "medium.en"]},
    "stt.device": {"choices": ["cpu", "cuda", "auto"]},
    "stt.compute_type": {"choices": ["int8", "float16", "int8_float16", "float32"]},
    "stt.cpu_threads": {"range": (1, 32, 1)},
    "brain.temperature": {"range": (0.0, 1.5, 0.05)},
    "brain.history_turns": {"range": (0, 40, 1)},
    "brain.timeout": {"range": (5, 300, 5)},
    "ui.scale": {"range": (0.15, 1.5, 0.01)},
    "ui.minimal_scale": {"range": (0.15, 1.5, 0.01)},
    "ui.position": {"choices": ["bottom-right", "bottom-left", "top-right", "top-left", "custom"]},
    "ui.mode": {"choices": ["normal", "minimal"]},
    "ui.hide_after": {"range": (1.0, 60.0, 0.5)},
    "ui.typewriter_cps": {"range": (5, 200, 1)},
    "ui.margin": {"range": (0, 400, 1)},
    "music.service": {"choices": ["youtube_music", "youtube", "spotify_web"]},
    "music.default": {"choices": ["liked", "home"]},
}
# Everything applies live now. These take a few seconds because a model reloads in the background.
RESTART: tuple[str, ...] = ()
RELOADS = ("stt.model", "stt.device", "stt.compute_type", "stt.cpu_threads", "voice.engine", "voice.device",
           "voice.reference")
HIDDEN = {"ui.custom_xy"}
LABELS = {"conversation.follow_up": "Keep listening after replies", "conversation.follow_up_seconds":
          "Listen after a reply (seconds)", "conversation.answer_seconds": "Listen after a question (seconds)",
          "personality.genz_slang": "Gen Z slang", "stt.model": "Whisper model", "brain.model": "AI model",
          "wake.end_silence": "Pause that ends a command", "wake.min_confidence": "Wake sensitivity (confidence)",
          "voice.duck_level": "Other apps while ducked", "voice.duck_others": "Lower other apps (ducking)",
          "voice.pronounce": "Pronunciations", "ui.typewriter_cps": "Text reveal speed",
          "stt.cpu_threads": "CPU threads", "brain.history_turns": "Conversation memory (turns)"}        # set by dragging Capri


@dataclass
class Field:
    key: str                     # dotted path
    default: Any
    help: str = ""
    section: str = ""
    spec: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return LABELS.get(self.key) or self.key.split(".")[-1].replace("_", " ").capitalize()

    @property
    def reloads(self) -> bool:
        return self.key in RELOADS

    @property
    def needs_restart(self) -> bool:
        return any(self.key == r or (r.endswith(".") and self.key.startswith(r)) for r in RESTART)


def load_fields() -> list[Field]:
    text = (paths.DEFAULTS_DIR / "settings.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    fields: list[Field] = []
    section = ""
    pending: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            pending = []
            continue
        top = re.match(r"^([a-z_]+):\s*(?:#.*)?$", line)
        if top:
            section, pending = top.group(1), []
            continue
        com = re.match(r"^\s+#\s?(.*)$", line)
        if com:
            if not re.match(r"^\s*[a-z_]+:\s", com.group(1)):      # skip commented-out examples
                pending.append(com.group(1).strip())
            continue
        kv = re.match(r"^  ([a-z_]+):(.*)$", line)
        if kv and section:
            key = f"{section}.{kv.group(1)}"
            inline = ""
            m = re.search(r"\s#\s?(.*)$", kv.group(2))
            if m:
                inline = m.group(1).strip()
            help_text = " ".join(pending + ([inline] if inline else [])).strip()
            pending = []
            if key in HIDDEN:
                continue
            default = (data.get(section) or {}).get(kv.group(1))
            fields.append(Field(key, default, help_text, section, SPECIAL.get(key, {})))
    return fields
