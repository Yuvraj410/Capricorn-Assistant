"""Global hotkey (default Ctrl+Alt+C) via the Win32 RegisterHotKey API - no extra packages, no admin."""
from __future__ import annotations

import ctypes
import logging
import sys
import threading
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger(__name__)

MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


def _parse(combo: str) -> tuple[int, int] | None:
    mods, vk = 0, None
    for part in combo.lower().replace(" ", "").split("+"):
        if part in MODS:
            mods |= MODS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit():
            vk = 0x70 + int(part[1:]) - 1
        elif part == "space":
            vk = 0x20
    return (mods, vk) if vk else None


class GlobalHotkey(QObject):
    triggered = pyqtSignal()

    def __init__(self, combo: str) -> None:
        super().__init__()
        self.combo = combo
        self._tid = None

    def start(self) -> None:
        if sys.platform != "win32":
            return
        parsed = _parse(self.combo)
        if not parsed:
            log.warning("bad hotkey %r", self.combo)
            return
        threading.Thread(target=self._loop, args=parsed, daemon=True, name="hotkey").start()

    def _loop(self, mods: int, vk: int) -> None:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()  # type: ignore[attr-defined]
        if not user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk):
            log.warning("hotkey %s is already used by another app", self.combo)
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                self.triggered.emit()
        user32.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if self._tid and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)  # type: ignore[attr-defined]
