"""Find windows and bring them to the front, so you can see what Capri opened.

Windows normally refuses to let a background program (like Capri) put another window in
front of the one you're using - new windows just flash in the taskbar. Capri briefly attaches
to the foreground window's input queue (the standard, documented workaround) and then
raises the window it opened.
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

IS_WIN = sys.platform == "win32"


@dataclass
class Win:
    hwnd: int
    title: str
    exe: str          # lower-case file name, e.g. "steamwebhelper.exe"
    cls: str = ""


def _exe_of(pid: int) -> str:
    k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    h = k32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        k32.CloseHandle(h)


def list_windows() -> list[Win]:
    """Visible top-level windows with a title, front-most first."""
    if not IS_WIN:
        return []
    from ctypes import wintypes as w
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    out: list[Win] = []

    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):   # GW_OWNER: skip owned popups
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                t = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, t, n + 1)
                c = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, c, 256)
                pid = w.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out.append(Win(int(hwnd), t.value, _exe_of(pid.value), c.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


def focus(hwnd: int) -> bool:
    if not IS_WIN:
        return False
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_tid and fg_tid != me and user32.AttachThreadInput(me, fg_tid, True))
    try:
        user32.ShowWindow(hwnd, 5)          # SW_SHOW
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_tid, False)
    for _ in range(10):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.05)
    return False


def allow_foreground() -> None:
    """Let the program we're about to launch take the foreground itself."""
    if IS_WIN:
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # type: ignore[attr-defined]  ASFW_ANY
        except Exception:
            pass


def bring_to_front(match: Callable[[Win], bool], timeout: float = 8.0, settle: float = 0.0,
                   background: bool = True) -> None:
    """Wait for a window matching `match` and focus it (in a background thread by default)."""
    if not IS_WIN:
        return

    def run() -> None:
        if settle:
            time.sleep(settle)
        end = time.time() + timeout
        while time.time() < end:
            for w in list_windows():
                if match(w):
                    if focus(w.hwnd):
                        log.info("focused %r (%s)", w.title, w.exe)
                    return
            time.sleep(0.3)
        log.info("no matching window appeared to focus")

    if background:
        threading.Thread(target=run, daemon=True, name="focus").start()
    else:
        run()


# -- matchers --------------------------------------------------------------------------------------
def _words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) >= 3]


def title_has(name: str) -> Callable[[Win], bool]:
    """Window whose title contains the main word(s) of `name` ("Visual Studio Code" -> 'visual')."""
    words = [w for w in _words(name) if w not in {"the", "and", "app", "for"}]
    if not words:
        return lambda w: False
    key = words[0]
    return lambda w: key in w.title.lower() and not w.title.lower().startswith("capri")


def exe_is(*exes: str) -> Callable[[Win], bool]:
    names = {e.lower() for e in exes}
    return lambda w: w.exe in names


def any_of(*matchers: Callable[[Win], bool]) -> Callable[[Win], bool]:
    return lambda w: any(m(w) for m in matchers)


BROWSER_EXES = {"opera.exe", "opera_gx.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "vivaldi.exe"}


def browser_window(w: Win) -> bool:
    return w.exe in BROWSER_EXES and w.title.strip() != ""


def explorer_folder(folder_name: str) -> Callable[[Win], bool]:
    name = folder_name.lower()
    return lambda w: w.cls == "CabinetWClass" and name in w.title.lower()
