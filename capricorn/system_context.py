"""What's going on on the PC right now - so Capri understands "pause this song", "close it",
"what am I playing?" without asking. Gathered on demand (~50-300 ms), cached for a couple of seconds.

    snapshot() -> {"media": [{"app", "title", "artist", "status"}...], "foreground": {"app", "title"},
                   "games": ["Cyberpunk 2077"], "time": "Sunday 9:30 PM"}
    describe(snapshot) -> short text block for the AI's prompt
Nothing here is stored or sent anywhere; it only goes into the local model's prompt.
"""
from __future__ import annotations

import asyncio
import ctypes
import datetime as dt
import logging
import os
import sys
import threading
import time
from typing import Any

log = logging.getLogger(__name__)
_cache: dict[str, Any] = {"t": 0.0, "snap": None}
_lock = threading.Lock()

# AppUserModelIDs / exe names -> friendly names
APP_NAMES = {
    "opera": "Opera GX", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "brave": "Brave",
    "spotify": "Spotify", "vlc": "VLC", "zunemusic": "Media Player", "microsoft.media": "Media Player",
    "discord": "Discord", "steam": "Steam", "steamwebhelper": "Steam", "explorer": "File Explorer",
    "code": "VS Code", "windowsterminal": "Terminal", "playnite": "Playnite",
}
STATUS = {4: "playing", 5: "paused", 3: "stopped", 2: "stopped", 1: "opening", 0: "closed"}


def friendly_app(raw: str) -> str:
    low = (raw or "").lower()
    for key, name in APP_NAMES.items():
        if key in low:
            return name
    base = os.path.basename(raw or "").split("!")[0]
    return os.path.splitext(base)[0] or (raw or "")


async def _media_async() -> list[dict]:
    from winrt.windows.media.control import (  # type: ignore
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )
    mgr = await Manager.request_async()
    out = []
    for s in mgr.get_sessions():
        try:
            info = s.get_playback_info()
            status = STATUS.get(int(info.playback_status), "unknown") if info is not None else "unknown"
            props = await s.try_get_media_properties_async()
            out.append({"app": friendly_app(s.source_app_user_model_id), "title": props.title or "",
                        "artist": props.artist or "", "status": status})
        except Exception:
            log.debug("media session unreadable", exc_info=True)
    out.sort(key=lambda m: m["status"] != "playing")
    return out


def media_sessions() -> list[dict]:
    if sys.platform != "win32":
        return []
    try:
        return asyncio.run(_media_async())
    except Exception:
        log.debug("media sessions failed", exc_info=True)
        return []


def foreground() -> dict:
    """App + window title the user is looking at (skips Capri's own windows)."""
    if sys.platform != "win32":
        return {}
    try:
        u32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = u32.GetForegroundWindow()
        if not hwnd:
            return {}
        buf = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(hwnd, buf, 512)
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = ""
        try:
            import psutil
            exe = psutil.Process(pid.value).name()
        except Exception:
            pass
        if pid.value == os.getpid() or exe.lower().startswith("python"):
            return {}
        return {"app": friendly_app(exe), "title": buf.value[:120]}
    except Exception:
        log.debug("foreground failed", exc_info=True)
        return {}


def running_games(index) -> list[str]:
    if index is None:
        return []
    try:
        from .actions.close import running_steam_games
        return [e.name for e, _ in running_steam_games(index)]
    except Exception:
        log.debug("running games failed", exc_info=True)
        return []


def snapshot(index=None, max_age: float = 2.0) -> dict:
    with _lock:
        if _cache["snap"] is not None and time.time() - _cache["t"] < max_age:
            return _cache["snap"]
    snap = {"media": media_sessions(), "foreground": foreground(), "games": running_games(index),
            "time": dt.datetime.now().strftime("%A %I:%M %p").replace(" 0", " ")}
    with _lock:
        _cache.update(t=time.time(), snap=snap)
    return snap


def playing(snap: dict) -> dict | None:
    return next((m for m in snap.get("media", []) if m["status"] == "playing"), None)


def describe(snap: dict) -> str:
    lines = [f"Time: {snap.get('time', '')}."]
    media = [m for m in snap.get("media", []) if m["title"] or m["status"] == "playing"]
    if media:
        for m in media[:3]:
            what = f"\"{m['title']}\"" + (f" by {m['artist']}" if m["artist"] else "") if m["title"] else "something"
            lines.append(f"Media: {what} in {m['app']} - {m['status'].upper()}.")
    else:
        lines.append("Media: nothing is playing.")
    fg = snap.get("foreground") or {}
    if fg:
        lines.append(f"User is looking at: {fg.get('app', '?')} - \"{fg.get('title', '')}\".")
    games = snap.get("games") or []
    lines.append(f"Running game: {', '.join(games)}." if games else "No game running.")
    return ("RIGHT NOW ON THE PC (live, use it to understand what the user means; \"this song\", \"the music\", "
            "\"it\" = the media that is PLAYING; \"this game\" = the running game. Never ask which song "
            "or game when it's listed here - just act):\n- " + "\n- ".join(lines))
