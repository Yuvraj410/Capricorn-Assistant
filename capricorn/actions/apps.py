"""Find and launch installed apps and games.

Sources (merged, refreshed in the background):
  1. Your Steam library (every installed game, launched through Steam)
  2. PowerShell `Get-StartApps` - every Start Menu entry, including Store/UWP apps
  3. .lnk / .url shortcuts on the Desktop and in the Start Menu folders (Epic/other games)
Launching goes through the Windows shell (no command line is ever built from user text).
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .. import match, persona
from ..security.permissions import ASK, DENY, Permissions
from .base import Result, log_action

log = logging.getLogger(__name__)


CREATE_NO_WINDOW = 0x08000000

# Spoken name -> what it's usually called in the Start Menu
ALIASES = {
    "vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
    "word": "word", "excel": "excel", "powerpoint": "powerpoint",
    "file explorer": "file explorer", "explorer": "file explorer",
    "settings": "settings", "calculator": "calculator", "notepad": "notepad",
    "terminal": "terminal", "command prompt": "command prompt", "task manager": "task manager",
    "opera": "opera gx browser", "opera gx": "opera gx browser",
    "chrome": "google chrome", "edge": "microsoft edge",
}

# Steam "apps" that aren't games
STEAM_SKIP = re.compile(r"(redistributable|proton|steam linux runtime|steamworks|directx|vc\+\+|"
                        r"dedicated server|sdk$|soundtrack)", re.I)

# Never launch these through voice, even in "all" mode (they run arbitrary code / change the system).
NEVER_LAUNCH = re.compile(r"\b(uninstall|regedit|registry editor|powershell|windows powershell ise)\b|^capri(con|corn)?$", re.I)


@dataclass
class AppEntry:
    name: str
    target: str     # AppID for shell:AppsFolder, a shortcut file path, or a Steam appid
    kind: str       # "appid" | "shortcut" | "steam"
    path: str = ""  # Steam: the game's install folder (to find its running processes)

    @property
    def is_game(self) -> bool:
        return self.kind == "steam" or (self.kind == "shortcut" and self.target.lower().endswith(".url"))


class AppIndex:
    def __init__(self) -> None:
        self.entries: list[AppEntry] = []
        self._lock = threading.Lock()
        self._last = 0.0

    def refresh_async(self) -> None:
        threading.Thread(target=self.refresh, daemon=True, name="app-index").start()

    def refresh(self) -> None:
        found: dict[str, AppEntry] = {}
        for e in self._steam_games():
            found.setdefault(e.name.lower(), e)
        if sys.platform == "win32":
            for e in self._start_apps():
                found.setdefault(e.name.lower(), e)
        for e in self._shortcuts():
            found.setdefault(e.name.lower(), e)
        with self._lock:
            self.entries = list(found.values())
            self._last = time.time()
        log.info("App index: %d entries", len(self.entries))

    @staticmethod
    def _steam_root() -> Path | None:
        if sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                    p = Path(winreg.QueryValueEx(k, "SteamPath")[0])
                    if p.exists():
                        return p
            except OSError:
                pass
            for p in (Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")):
                if p.exists():
                    return p
        else:
            p = Path.home() / ".steam" / "steam"
            return p if p.exists() else None
        return None

    @classmethod
    def _steam_games(cls, root: Path | None = None) -> list[AppEntry]:
        root = root or cls._steam_root()
        if not root:
            return []
        libs = {root / "steamapps"}
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
                libs.add(Path(m.group(1).replace("\\\\", "\\")) / "steamapps")
        except OSError:
            pass
        out: list[AppEntry] = []
        for lib in libs:
            try:
                manifests = list(lib.glob("appmanifest_*.acf"))
            except OSError:
                continue
            for acf in manifests:
                try:
                    txt = acf.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                aid = re.search(r'"appid"\s+"(\d+)"', txt)
                name = re.search(r'"name"\s+"([^"]+)"', txt)
                inst = re.search(r'"installdir"\s+"([^"]+)"', txt)
                if aid and name and not STEAM_SKIP.search(name.group(1)):
                    folder = str(lib / "common" / inst.group(1)) if inst else ""
                    out.append(AppEntry(name.group(1), aid.group(1), "steam", folder))
        return out

    @staticmethod
    def _start_apps() -> list[AppEntry]:
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW,
            ).stdout
            data = json.loads(out or "[]")
            if isinstance(data, dict):
                data = [data]
            return [AppEntry(d["Name"], d["AppID"], "appid") for d in data if d.get("Name") and d.get("AppID")]
        except Exception:
            log.exception("Get-StartApps failed")
            return []

    @staticmethod
    def _shortcuts() -> list[AppEntry]:
        dirs = [Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"]
        if sys.platform == "win32":
            dirs += [Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
                     Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
                     Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs"]
        out: list[AppEntry] = []
        for d in dirs:
            if not d.is_dir():
                continue
            depth0 = len(d.parts)
            for root, subdirs, files in os.walk(d):
                if len(Path(root).parts) - depth0 >= 3:
                    subdirs[:] = []
                for f in files:
                    if f.lower().endswith((".lnk", ".url")):
                        name = f.rsplit(".", 1)[0]
                        if NEVER_LAUNCH.search(name):
                            continue
                        out.append(AppEntry(name, str(Path(root) / f), "shortcut"))
        return out

    def _normalize(self, spoken: str) -> str:
        q = spoken.lower().strip()
        q = re.sub(r"^(the|my)\s+", "", q)
        q = re.sub(r"\s+(app|application|game|program)$", "", q)
        q = re.sub(r"\s+(on|in|via|using|with|from|through)\s+steam$", "", q)
        q = re.sub(r"\s+(for me|please|now)$", "", q)
        return ALIASES.get(q, q)

    def _match(self, q: str, entries: list[AppEntry], cutoff: float) -> AppEntry | None:
        if not entries or not q:
            return None
        i = match.best(q, [e.name for e in entries], minimum=cutoff)
        return entries[i] if i is not None else None

    def _entries(self) -> list[AppEntry]:
        if time.time() - self._last > 1800:
            self.refresh_async()
        with self._lock:
            ents = [e for e in self.entries if not NEVER_LAUNCH.search(e.name)]
        return sorted(ents, key=lambda e: not e.is_game)   # games first

    def find(self, spoken: str) -> AppEntry | None:
        return self._match(self._normalize(spoken), self._entries(), 80)

    def suggest(self, spoken: str, games_only: bool = False, minimum: float = 70.0) -> AppEntry | None:
        """Closest-sounding app/game for 'Did you mean ...?' when nothing matched exactly."""
        q = self._normalize(spoken)
        ents = [e for e in self._entries() if e.is_game or not games_only]
        best_e, best_s = None, 0.0
        for e in ents:
            s = match.sounds_like(q, e.name) + (3 if e.is_game else 0)
            if s > best_s:
                best_e, best_s = e, s
        return best_e if best_s >= minimum else None

    def steam_games(self) -> list[AppEntry]:
        return [e for e in self._entries() if e.kind == "steam"]

    def game_names(self, limit: int = 60) -> list[str]:
        return [e.name for e in self._entries() if e.is_game][:limit]

    def find_game(self, spoken: str) -> AppEntry | None:
        """Only installed games, with a stricter match - used for 'play <x>'."""
        return self._match(self._normalize(spoken), [e for e in self._entries() if e.is_game], 80)


def _shortcut_exe(path: str) -> str:
    """Target .exe of a .lnk (to recognise its window later)."""
    if not path.lower().endswith(".lnk"):
        return ""
    try:
        import win32com.client  # type: ignore
        target = win32com.client.Dispatch("WScript.Shell").CreateShortcut(path).TargetPath
        return os.path.basename(target).lower() if target.lower().endswith(".exe") else ""
    except Exception:
        return ""


def _launch(entry: AppEntry) -> None:
    from . import steam, windows
    if entry.kind == "steam":
        steam.launch_installed(entry.target, entry.name)   # library page first, then launch
        return
    windows.allow_foreground()
    exe = ""
    if entry.kind == "appid":
        # explorer resolves the Start Menu item exactly like clicking it
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{entry.target}"], close_fds=True)
        if entry.target.lower().endswith(".exe"):
            exe = os.path.basename(entry.target).lower()
    else:
        os.startfile(entry.target)  # type: ignore[attr-defined]  (Windows only)
        exe = _shortcut_exe(entry.target)
    # Bring the app's window to the front so you can see it (Windows won't do that for us).
    matchers = [windows.title_has(entry.name)]
    if exe:
        matchers.append(windows.exe_is(exe))
    if entry.name.lower() == "steam":
        from .steam import steam_window
        matchers = [steam_window]
    windows.bring_to_front(windows.any_of(*matchers), timeout=10, settle=0.6)


def open_app(name: str, index: AppIndex, perms: Permissions) -> Result:
    entry = index.find(name)
    if entry is None:
        return Result(False, *persona.line("not_found"))
    d = perms.check_app(entry.name)
    if d.verdict == DENY:
        log_action("open_app", entry.name, "denied")
        return Result(False, *persona.line("denied", reason=d.reason))

    def run() -> Result:
        try:
            _launch(entry)
            log_action("open_app", f"{entry.name} -> {entry.target}", "ok")
            key = ("open_app_steam" if entry.name.lower() == "steam" else
                   "steam_launch" if entry.kind == "steam" else "game" if entry.is_game else "open_app")
            return Result(True, *persona.line(key, name=entry.name))
        except Exception:
            log.exception("launch failed: %s", entry)
            return Result(False, *persona.line("error"))

    if d.verdict == ASK:
        return Result(True, "", "surprised", confirm_question=f"Launch {entry.name}?", confirm_run=run, approve=(d.category, d.key))
    return run()
