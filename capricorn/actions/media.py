"""Media control for whatever is playing - including the YouTube Music player in the
Opera GX sidebar, Spotify, browsers, etc.

* Commands are sent as hardware media keys (exactly like pressing Play/Pause on a keyboard),
  which Windows routes to the active media session.
* "What's playing?" reads Windows' media session info (SMTC) through the winrt packages.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import sys

from .. import persona
from ..security.permissions import ASK, DENY, Permissions
from .base import Result, log_action

log = logging.getLogger(__name__)

VK = {
    "play_pause": 0xB3, "pause": 0xB3, "play": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2,
    "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD,
}
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x1, 0x2


def _tap(vk: int, times: int = 1) -> None:
    if sys.platform != "win32":
        log.info("media key %s (no-op on this OS)", hex(vk))
        return
    u32 = ctypes.windll.user32  # type: ignore[attr-defined]
    for _ in range(times):
        u32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
        u32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


SMTC_METHODS = {"play_pause": "try_toggle_play_pause_async", "pause": "try_pause_async",
                "play": "try_play_async", "next": "try_skip_next_async",
                "previous": "try_skip_previous_async", "stop": "try_pause_async"}


async def _smtc_async(command: str) -> bool:
    """Send play/pause/next/previous straight to the player through Windows' media controls
    (what the taskbar / Quick Settings media buttons use). Prefers the session that's playing."""
    from winrt.windows.media.control import (  # type: ignore
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )
    mgr = await Manager.request_async()
    sessions = list(mgr.get_sessions())
    if not sessions:
        return False

    def status(sess) -> int:
        info = sess.get_playback_info()
        return int(info.playback_status) if info is not None else 0

    playing = [x for x in sessions if status(x) == 4]
    current = mgr.get_current_session()
    if command == "pause" and not playing:
        return True                     # nothing playing: already "paused"
    if command in ("play_pause", "play") and not playing:
        # nothing playing -> resume the most recent paused one
        target = current or next((x for x in sessions if status(x) == 5), sessions[0])
    else:
        target = playing[0] if playing else (current or sessions[0])
    ok = await getattr(target, SMTC_METHODS[command])()
    log.info("SMTC %s -> %s: %s", command, target.source_app_user_model_id, ok)
    return bool(ok)


def _smtc(command: str) -> bool:
    if sys.platform != "win32" or command not in SMTC_METHODS:
        return False
    try:
        return asyncio.run(_smtc_async(command))
    except Exception:
        log.warning("SMTC %s failed - falling back to media keys", command, exc_info=True)
        return False


def media(command: str, perms: Permissions) -> Result:
    command = (command or "").lower().strip().replace(" ", "_")
    command = {"resume": "play", "unpause": "play", "continue": "play", "stop": "pause", "toggle": "play_pause",
               "skip": "next", "back": "previous", "prev": "previous"}.get(command, command)
    if command not in VK:
        return Result(False, *persona.line("not_understood"))
    d = perms.check_media()
    if d.verdict == DENY:
        return Result(False, *persona.line("denied", reason=d.reason))

    def run() -> Result:
        playing_now = is_playing() if command in ("pause", "play") else None
        if command == "pause" and playing_now is False:
            return Result(True, *persona.line("media_already_paused"))
        if command == "play" and playing_now is True:
            return Result(True, *persona.line("media_already_playing"))
        # play/pause/next/previous: talk to the player directly; keys only as a fallback
        if not _smtc(command):
            # volume keys move ~2% per tap on Windows; 5 taps = ~10%
            _tap(VK[command], 5 if command.startswith("volume") else 1)
        log_action("media", command, "ok")
        return Result(True, *persona.line(f"media_{command}"))

    if d.verdict == ASK:
        return Result(True, "", "surprised", confirm_question=f"Media: {command.replace('_', ' ')}?", confirm_run=run, approve=(d.category, d.key))
    return run()


async def _now_playing_async() -> tuple[str, str] | None:
    from winrt.windows.media.control import (  # type: ignore
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )
    mgr = await Manager.request_async()
    session = mgr.get_current_session()
    if session is None:
        return None
    props = await session.try_get_media_properties_async()
    return (props.title or "", props.artist or "")


async def _is_playing_async() -> bool:
    from winrt.windows.media.control import (  # type: ignore
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )
    mgr = await Manager.request_async()
    for session in mgr.get_sessions():
        info = session.get_playback_info()
        if info is not None and int(info.playback_status) == 4:   # 4 = Playing
            return True
    return False


def is_playing() -> bool | None:
    """True if any app (browser tab, Opera GX sidebar, Spotify...) is playing media.
    None if it can't be determined (not Windows / winrt missing)."""
    if sys.platform != "win32":
        return None
    try:
        return asyncio.run(_is_playing_async())
    except ImportError:
        return None
    except Exception:
        log.debug("is_playing failed", exc_info=True)
        return None


def now_playing(perms: Permissions) -> Result:
    d = perms.check_media()
    if d.verdict == DENY:
        return Result(False, *persona.line("denied", reason=d.reason))
    if sys.platform != "win32":
        return Result(True, *persona.line("nothing_playing"))
    try:
        info = asyncio.run(_now_playing_async())
    except ImportError:
        log.warning("winrt media packages not installed")
        return Result(False, "Can't read what's playing - the media add-on isn't installed. Run setup again.", "sad")
    except Exception:
        log.exception("now_playing failed")
        info = None
    if not info or not info[0]:
        return Result(True, *persona.line("nothing_playing"))
    title = info[0] + (f" by {info[1]}" if info[1] else "")
    return Result(True, *persona.line("now_playing", title=title))
