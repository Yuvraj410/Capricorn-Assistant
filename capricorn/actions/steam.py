"""Steam, done the visible way.

Installed game  -> Steam comes to the front on the game's library page, then the game launches.
Not installed   -> Capri finds the game on the Steam store (free public search, no account/key),
                   opens it in Steam - your library page if you own it (shows the Install button),
                   otherwise its store page - and tells you to install it first.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

from .. import match, persona
from ..security.permissions import ASK, DENY, Permissions
from . import windows
from .base import Result, log_action

log = logging.getLogger(__name__)

STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"


def steam_root() -> Path | None:
    from .apps import AppIndex
    return AppIndex._steam_root()


def available() -> bool:
    return steam_root() is not None


def _open(url: str) -> None:
    windows.allow_foreground()
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        log.info("would open %s", url)


def steam_window(w: windows.Win) -> bool:
    t = w.title.strip().lower()
    return (t == "steam" or t.startswith("steam ")) and w.exe in {"steam.exe", "steamwebhelper.exe", ""}


def _show_steam(delay: float = 0.0) -> None:
    windows.bring_to_front(steam_window, timeout=10, settle=delay)


# -- ownership (best effort, from Steam's local config) ------------------------------------------
_owned_cache: tuple[float, set[str]] = (0.0, set())


def _vdf_block(text: str, key: str) -> str:
    """Contents of the first `"key" { ... }` block (brace-matched)."""
    m = re.search(r'"%s"\s*\{' % re.escape(key), text, re.I)
    if not m:
        return ""
    depth, i = 1, m.end()
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[m.end(): i - 1]


def owned_appids(root: Path | None = None) -> set[str]:
    """App ids listed in userdata/*/config/localconfig.vdf (games this Steam account has)."""
    global _owned_cache
    if time.time() - _owned_cache[0] < 600 and _owned_cache[1]:
        return _owned_cache[1]
    root = root or steam_root()
    ids: set[str] = set()
    if root:
        for cfg in (root / "userdata").glob("*/config/localconfig.vdf"):
            try:
                txt = cfg.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            steam = _vdf_block(_vdf_block(_vdf_block(txt, "Software"), "Valve"), "Steam") or txt
            apps = _vdf_block(steam, "apps")
            ids |= set(re.findall(r'^\s*"(\d{2,9})"\s*$', apps, re.M))
    _owned_cache = (time.time(), ids)
    return ids


# -- store search ----------------------------------------------------------------------------------
def store_search(name: str, timeout: float = 6.0) -> list[tuple[str, str]]:
    """[(appid, title)] from the public Steam store search."""
    import requests
    try:
        r = requests.get(STORE_SEARCH, params={"term": name, "l": "english", "cc": "US"}, timeout=timeout)
        r.raise_for_status()
        return [(str(i["id"]), i.get("name", "")) for i in r.json().get("items", []) if i.get("id")]
    except Exception as e:
        log.warning("Steam store search failed: %s", e)
        return []


def best_store_match(name: str, results: list[tuple[str, str]]) -> tuple[str, str] | None:
    best, top = None, 0.0
    for appid, title in results:
        s = max(match.score(name, title), match.sounds_like(name, title))
        if s > top:
            best, top = (appid, title), s
    return best if top >= 82 else None


# -- actions ----------------------------------------------------------------------------------------
def launch_installed(appid: str, name: str) -> None:
    """Show the game's library page in Steam, then launch it (runs in the background)."""
    def run() -> None:
        _open(f"steam://nav/games/details/{appid}")
        windows.bring_to_front(steam_window, timeout=8, background=False)
        time.sleep(1.5)                    # let you see the library page
        _open(f"steam://rungameid/{appid}")
        log.info("launched %s (%s) via Steam", name, appid)
    threading.Thread(target=run, daemon=True, name="steam-launch").start()


def open_not_installed(name: str, perms: Permissions) -> Result | None:
    """Game isn't installed: open it in Steam and tell the user to install it. None if not found."""
    if not available():
        return None
    hit = best_store_match(name, store_search(name))
    if not hit:
        return None
    appid, title = hit
    d = perms.check_app("Steam")
    if d.verdict == DENY:
        return Result(False, *persona.line("denied", reason=d.reason))
    owned = appid in owned_appids()
    url = f"steam://nav/games/details/{appid}" if owned else f"steam://store/{appid}"

    def run() -> Result:
        _open(url)
        _show_steam(delay=0.5)
        log_action("steam_page", f"{title} ({appid}) owned={owned}", "ok")
        key = "steam_not_installed" if owned else "steam_not_owned"
        return Result(True, *persona.line(key, name=title))

    if d.verdict == ASK:
        return Result(True, "", "surprised", confirm_question=f"Open {title} in Steam?", confirm_run=run,
                      approve=(d.category, d.key))
    return run()
