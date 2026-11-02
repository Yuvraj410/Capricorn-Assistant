"""Closing games and apps.

Steam game: the game is asked to close normally (like clicking its X, so it can save); if it's
still running after a few seconds it is stopped - exactly what Steam's Stop button does (Steam
has no command-line/URL for that button). Then Steam is shown on the game's page.
Set games.ask_before_force_stop: true to be asked before the stop.
Other apps: their windows are asked to close normally. Nothing is ever force-closed without asking.
"""
from __future__ import annotations

import logging
import os
import sys
import time

from .. import persona
from ..security.permissions import DENY, Permissions
from . import windows
from .apps import AppEntry, AppIndex
from .base import Result, log_action

log = logging.getLogger(__name__)

WM_CLOSE = 0x0010
NEVER_CLOSE = {"explorer.exe", "dwm.exe", "csrss.exe", "winlogon.exe", "python.exe", "pythonw.exe",
               "ollama.exe", "ollama app.exe"}


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p)) if p else ""


def game_processes(folder: str) -> list:
    """Running processes whose executable lives inside the game's install folder."""
    import psutil
    root = _norm(folder)
    if not root:
        return []
    out = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        exe = proc.info.get("exe") or ""
        if exe and _norm(exe).startswith(root + os.sep):
            out.append(proc)
    return out


def running_steam_games(index: AppIndex) -> list[tuple[AppEntry, list]]:
    return [(g, procs) for g in index.steam_games() if g.path for procs in [game_processes(g.path)] if procs]


def _close_windows_of(pids: set[int]) -> int:
    """Politely ask every top-level window of these processes to close (like clicking X)."""
    if sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes as w
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    sent = 0
    for win in windows.list_windows():
        pid = w.DWORD()
        user32.GetWindowThreadProcessId(win.hwnd, ctypes.byref(pid))
        if pid.value in pids:
            user32.PostMessageW(win.hwnd, WM_CLOSE, 0, 0)
            sent += 1
    return sent


def _wait_gone(procs: list, timeout: float) -> list:
    import psutil
    _gone, alive = psutil.wait_procs(procs, timeout=timeout)
    return alive


def close_game(name: str, index: AppIndex, perms: Permissions, grace: float = 4.0, ask: bool = False) -> Result:
    """Close a running Steam game like Steam's Stop button: ask it to quit, then end it."""
    running = running_steam_games(index)
    if name.strip():
        game = index.find_game(name) or index.suggest(name, games_only=True, minimum=80)
        if game is None:
            return Result(False, *persona.line("not_found"))
        running = [(g, p) for g, p in running if g.target == game.target]
        if not running:
            return Result(True, *persona.line("close_not_running", name=game.name))
    elif not running:
        return Result(True, *persona.line("close_nothing_running"))
    game, procs = running[0]
    d = perms.check_app(game.name)
    if d.verdict == DENY:
        return Result(False, *persona.line("denied", reason=d.reason))

    def show_steam() -> None:
        # only AFTER the game is gone - focusing Steam earlier just minimizes a fullscreen game
        from . import steam
        try:
            steam._open(f"steam://nav/games/details/{game.target}")
            steam._show_steam(delay=0.3)
        except Exception:
            log.debug("couldn't show Steam", exc_info=True)

    def force(still: list) -> None:
        import psutil
        for p in still:
            try:
                for child in p.children(recursive=True):
                    child.kill()
                p.kill()
            except psutil.Error:
                pass
        _wait_gone(still, 5)

    _close_windows_of({p.pid for p in procs})
    alive = _wait_gone(procs, grace)
    if not alive:
        log_action("close_game", game.name, "ok")
        show_steam()
        return Result(True, *persona.line("close_game", name=game.name))
    if not ask:
        force([p for p in alive if p.is_running()])
        log_action("close_game", f"{game.name} (stopped)", "ok")
        show_steam()
        return Result(True, *persona.line("close_game_forced", name=game.name))

    def confirmed() -> Result:
        force([p for p in alive if p.is_running()])
        log_action("close_game", f"{game.name} (force-stopped)", "ok")
        show_steam()
        return Result(True, *persona.line("close_game_forced", name=game.name))

    return Result(True, "", "surprised",
                  confirm_question=f"{game.name} didn't close by itself. Force-stop it like Steam's Stop button? "
                                   "Unsaved progress will be lost.",
                  confirm_run=confirmed)


def close_app(name: str, index: AppIndex, perms: Permissions) -> Result:
    """Close an app's windows politely. Steam games go through close_game."""
    game = index.find_game(name)
    if game is not None and game.kind == "steam":
        return close_game(game.name, index, perms)
    entry = index.find(name)
    label = entry.name if entry else name.strip()
    d = perms.check_app(label)
    if d.verdict == DENY:
        return Result(False, *persona.line("denied", reason=d.reason))
    match = windows.title_has(label)
    exe = ""
    if entry is not None and entry.kind == "shortcut":
        from .apps import _shortcut_exe
        exe = _shortcut_exe(entry.target)
    targets = [w for w in windows.list_windows()
               if w.exe not in NEVER_CLOSE and (match(w) or (exe and w.exe == exe))
               and not (w.exe in windows.BROWSER_EXES and not _is_browser_name(label))]
    if not targets:
        return Result(True, *persona.line("close_not_running", name=label))
    if sys.platform == "win32":
        import ctypes
        for w in targets:
            ctypes.windll.user32.PostMessageW(w.hwnd, WM_CLOSE, 0, 0)  # type: ignore[attr-defined]
    time.sleep(0.3)
    log_action("close_app", f"{label} ({len(targets)} window(s))", "ok")
    return Result(True, *persona.line("close_app", name=label))


def _is_browser_name(name: str) -> bool:
    n = name.lower()
    return any(b in n for b in ("opera", "chrome", "edge", "firefox", "brave", "vivaldi", "browser"))
