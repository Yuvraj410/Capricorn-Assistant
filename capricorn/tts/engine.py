"""Spoken replies. voice.engine:
    auto  - Capri's own voice if it's installed (commands\\install-capri-voice.bat), else text only
    capri - Capri's own voice: local Chatterbox Turbo cloning capricorn-data/voices/capri.wav (free, offline)
    sapi  - free built-in Windows voice (not Capri's voice, but it talks)
    none  - text bubbles only
Plus a pre-recorded line cache: capricorn-data/voice_cache/index.json maps exact lines to .wav
files (made by tools/split_voice_lines.py). When a reply matches, that clip plays instead.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from .. import paths
from ..config import Settings
from . import textprep

log = logging.getLogger(__name__)


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("'", ""))).strip()


class TTS:
    """speak() is non-blocking. Hooks (called from a background thread):
       on_chunk(ms)       a piece of audio of `ms` milliseconds starts playing (drive the talking animation)
       on_done(completed) the reply finished playing (or was interrupted / never started)."""

    def __init__(self, settings: Settings, on_status: Callable[[str], None] = lambda s: None,
                 on_ready: Callable[[], None] = lambda: None) -> None:
        self.s = settings
        self.on_status = on_status
        self.on_ready = on_ready
        self._cache: dict[str, Path] = {}
        self.capri = None
        self._load_cache()

    # -- setup -------------------------------------------------------------------------------------
    def engine(self) -> str:
        e = str(self.s.get("voice.engine", "auto")).lower()
        if e == "auto":
            from .capri_voice import CapriVoice
            return "capri" if CapriVoice.installed() and self.reference().exists() else "none"
        return e

    def reference(self) -> Path:
        ref = Path(str(self.s.get("voice.reference", "capri.wav")))
        return ref if ref.is_absolute() else paths.voices_dir() / ref

    def start(self) -> None:
        if self.engine() != "capri":
            return
        from .capri_voice import CapriVoice
        if not CapriVoice.installed():
            self.on_status("Capri's voice isn't installed - run commands\\install-capri-voice.bat")
            return
        self.capri = CapriVoice(self.reference(), device=str(self.s.get("voice.device", "auto")),
                                seed=int(self.s.get("voice.seed", 7)),
                                temperature=float(self.s.get("voice.temperature", 0.8)),
                                loudness=float(self.s.get("voice.loudness", -16.0)),
                                volume=float(self.s.get("voice.volume", 1.0)),
                                on_status=self.on_status, on_ready=self.on_ready)
        self.capri.start()
        from .. import persona
        self.prewarm([line for key, lines in persona.LINES.items() for line in lines])

    def apply_settings(self, changed: set[str]) -> None:
        """Voice settings changed in the settings screen - apply without restarting Capri."""
        if changed & {"voice.engine", "voice.device", "voice.reference"}:
            self.close()                   # the voice model reloads in the background (~25 s on a GPU)
            self.capri = None
            self.start()
            return
        if self.capri:
            self.capri.seed = int(self.s.get("voice.seed", 7))
            self.capri.temperature = float(self.s.get("voice.temperature", 0.8))
            self.capri.loudness = float(self.s.get("voice.loudness", -16.0))
            self.capri.player.volume = float(self.s.get("voice.volume", 1.0))
            if "voice.prewarm" in changed or "voice.pronounce" in changed or "voice.emotion_tags" in changed:
                from .. import persona
                self.prewarm([line for lines in persona.LINES.values() for line in lines])

    def set_volume(self, volume: float) -> None:
        if self.capri:
            self.capri.player.volume = volume

    def close(self) -> None:
        if self.capri:
            self.capri.close()

    def _load_cache(self) -> None:
        idx = paths.voice_cache_dir() / "index.json"
        if not idx.exists():
            return
        try:
            data = json.loads(idx.read_text(encoding="utf-8"))
            for item in data:
                p = paths.voice_cache_dir() / item["file"]
                if p.exists():
                    self._cache[_key(item["text"])] = p
            log.info("voice cache: %d lines", len(self._cache))
        except Exception:
            log.exception("voice cache index unreadable")

    def has_cached(self, text: str) -> bool:
        return _key(text) in self._cache

    def instant(self, text: str, emotion: str = "") -> bool:
        """Can this be spoken with no synthesis delay (recorded line or already-cached clip)?"""
        if self.s.get("voice.cached_lines", True) and _key(text) in self._cache and sys.platform == "win32":
            return True
        if self.engine() == "capri" and self.capri is not None:
            parts = textprep.for_speech(text, emotion, tags=bool(self.s.get("voice.emotion_tags", True)),
                                      pronounce=self.s.get("voice.pronounce", {}) or {})
            style = textprep.STYLE.get(emotion, "")
            return bool(parts) and all(self.capri.cache_file(p, style).exists() for p in parts)
        return False

    def prewarm(self, lines: list[tuple[str, str]]) -> None:
        """Synthesize Capri's fixed lines in the background while idle, so they play instantly later.
        Lines with a recorded clip are skipped (the recording is better)."""
        if not (self.capri and self.s.get("voice.prewarm", True)):
            return
        tags = bool(self.s.get("voice.emotion_tags", True))
        items = []
        for text, emo in lines:
            if "{" in text or _key(text) in self._cache:
                continue
            for part in textprep.for_speech(text, emo, tags=tags, pronounce=self.s.get("voice.pronounce", {}) or {}):
                items.append((part, textprep.STYLE.get(emo, "")))
        self.capri.prewarm(items)

    # -- speaking ------------------------------------------------------------------------------------
    def speak(self, text: str, emotion: str = "", on_chunk: Callable[[int], None] = lambda ms: None,
              on_done: Callable[[bool], None] = lambda ok: None) -> bool:
        """Returns True if something will be spoken (on_done fires later), False if not
        (on_done is NOT called then - carry on immediately)."""
        if not text:
            return False
        if self.s.get("voice.cached_lines", True) and _key(text) in self._cache and sys.platform == "win32":
            if self.capri:
                self.capri.stop()
            clip = self._cache[_key(text)]
            threading.Thread(target=self._play_clip, args=(clip, on_chunk, on_done), daemon=True).start()
            return True
        engine = self.engine()
        if engine == "capri" and self.capri is not None:
            parts = textprep.for_speech(text, emotion, tags=bool(self.s.get("voice.emotion_tags", True)),
                                      pronounce=self.s.get("voice.pronounce", {}) or {})
            return self.capri.speak(parts, on_chunk, on_done, style=textprep.STYLE.get(emotion, ""))
        if engine == "sapi" and sys.platform == "win32":
            threading.Thread(target=self._sapi_say, args=(text,), daemon=True).start()
        return False

    def _play_clip(self, clip: Path, on_chunk, on_done) -> None:
        from .capri_voice import Player, wav_ms
        ok = False
        try:
            on_chunk(wav_ms(clip))
            self._clip_player = Player(float(self.s.get("voice.volume", 1.0)))
            ok = self._clip_player.play(clip)
        except Exception:
            log.exception("cached clip failed")
        on_done(ok)

    def _sapi_say(self, text: str) -> None:
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Speak(text)
        except Exception:
            log.exception("SAPI speak failed")

    def stop(self) -> None:
        if self.capri:
            self.capri.stop()
        p = getattr(self, "_clip_player", None)
        if p:
            p.stop()


def play_sound(name: str) -> None:
    """Short UI sounds from assets/sounds (wake, done, error)."""
    p = paths.ASSETS_DIR / "sounds" / f"{name}.wav"
    if sys.platform == "win32" and p.exists():
        import winsound
        winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
