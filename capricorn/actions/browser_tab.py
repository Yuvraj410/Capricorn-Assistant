"""Reuse an already-open YouTube / YouTube Music tab instead of opening a new one.

Windows only exposes each browser window's *active* tab (through the window title, e.g.
"Shelter - YouTube Music - Opera"). If such a window exists, Capri brings it to the front and
navigates that tab: Ctrl+L (address bar) -> types the URL -> Enter. Otherwise returns False and
the caller opens a new tab as usual. Nothing is clicked; your clipboard is not touched.
"""
from __future__ import annotations

import ctypes
import logging
import re
import sys
import time
from urllib.parse import urlparse

log = logging.getLogger(__name__)

BROWSER_SUFFIX = re.compile(r" - (Opera|Opera GX|Google Chrome|Microsoft​? Edge|Brave|Vivaldi|Chromium|Mozilla Firefox)$")
TARGETS = {
    "music.youtube.com": [re.compile(r"YouTube Music")],
    "www.youtube.com": [re.compile(r" - YouTube(?! Music)"), re.compile(r"^YouTube(?! Music)")],
    "youtube.com": [re.compile(r" - YouTube(?! Music)"), re.compile(r"^YouTube(?! Music)")],
}


def _windows():
    if sys.platform != "win32":
        return []
    from ctypes import wintypes as w
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    found = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def find_tab_window(url: str, windows=None) -> tuple[int, str] | None:
    """Browser window whose active tab matches the URL's site (testable without Windows)."""
    host = (urlparse(url).hostname or "").lower()
    pats = TARGETS.get(host)
    if not pats:
        return None
    for hwnd, title in (windows if windows is not None else _windows()):
        m = BROWSER_SUFFIX.search(title)
        if not m:
            continue
        page = title[: m.start()]
        if any(p.search(page) for p in pats):
            return hwnd, title
    return None


# -- Win32 input --------------------------------------------------------------------------------
def _send_keys(events) -> None:
    from ctypes import wintypes as w

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD),
                    ("time", w.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", w.DWORD), ("u", _U)]

    arr = (INPUT * len(events))()
    for i, (vk, scan, flags) in enumerate(events):
        arr[i].type = 1   # INPUT_KEYBOARD
        arr[i].u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    ctypes.windll.user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))  # type: ignore[attr-defined]


KEYUP, UNICODE = 0x2, 0x4
VK_CONTROL, VK_RETURN, VK_L, VK_ESCAPE = 0x11, 0x0D, 0x4C, 0x1B


def _focus(hwnd: int) -> bool:
    from .windows import focus
    return focus(hwnd)


def reuse_tab(url: str) -> bool:
    """Navigate an open YouTube / YouTube Music tab to `url`. True if it worked."""
    if sys.platform != "win32":
        return False
    hit = find_tab_window(url)
    if not hit:
        return False
    hwnd, title = hit
    try:
        if not _focus(hwnd):
            log.info("couldn't focus %r - opening a new tab instead", title)
            return False
        time.sleep(0.15)
        # Ctrl+L -> address bar, type the URL, Enter
        _send_keys([(VK_CONTROL, 0, 0), (VK_L, 0, 0), (VK_L, 0, KEYUP), (VK_CONTROL, 0, KEYUP)])
        time.sleep(0.12)
        ev = []
        for ch in url:
            ev += [(0, ord(ch), UNICODE), (0, ord(ch), UNICODE | KEYUP)]
        ev += [(VK_RETURN, 0, 0), (VK_RETURN, 0, KEYUP)]
        _send_keys(ev)
        log.info("reused tab %r for %s", title, url)
        return True
    except Exception:
        log.exception("tab reuse failed")
        return False


VK_W = 0x57


def pick_tab_window(name: str, wins) -> tuple[int, str] | None:
    """Browser window to close a tab in. `wins` = [(hwnd, title, exe, is_foreground)] front-most first.
    With a site name: the window whose visible tab title mentions it. Without: the browser you're in."""
    from .windows import BROWSER_EXES
    browsers = [(h, t, fg) for h, t, exe, fg in wins if exe in BROWSER_EXES or BROWSER_SUFFIX.search(t)]
    if not browsers:
        return None
    if name:
        key = name.lower().replace(" ", "")
        for h, t, _fg in browsers:
            if key in t.lower().replace(" ", ""):
                return h, t
        return None
    for h, t, fg in browsers:
        if fg:
            return h, t
    return browsers[0][0], browsers[0][1]


def close_tab(name: str = "") -> tuple[bool, str]:
    """Close the visible tab of a browser window with Ctrl+W. Returns (closed, tab title)."""
    if sys.platform != "win32":
        return False, ""
    from . import windows
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    fg = user32.GetForegroundWindow()
    wins = [(w.hwnd, w.title, w.exe, w.hwnd == fg) for w in windows.list_windows()]
    hit = pick_tab_window(name, wins)
    if not hit:
        return False, ""
    hwnd, title = hit
    if not windows.focus(hwnd):
        return False, title
    time.sleep(0.15)
    _send_keys([(VK_CONTROL, 0, 0), (VK_W, 0, 0), (VK_W, 0, KEYUP), (VK_CONTROL, 0, KEYUP)])
    log.info("closed tab %r", title)
    return True, title
