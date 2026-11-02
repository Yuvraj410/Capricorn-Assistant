"""Open folders and files by name or path, inside the folders your permissions allow."""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path

from .. import match, persona
from ..security.permissions import ASK, DENY, Permissions
from .base import Result, log_action

log = logging.getLogger(__name__)



def _known_folders() -> dict[str, Path]:
    h = Path.home()
    od = h / "OneDrive"
    def pick(name: str) -> Path:
        p = h / name
        return p if p.exists() or not (od / name).exists() else od / name
    known = {
        "desktop": pick("Desktop"), "downloads": h / "Downloads", "download": h / "Downloads",
        "documents": pick("Documents"), "docs": pick("Documents"), "pictures": pick("Pictures"),
        "photos": pick("Pictures"), "music": h / "Music", "videos": h / "Videos",
        "home": h, "user folder": h, "screenshots": pick("Pictures") / "Screenshots",
    }
    if sys.platform == "win32":
        known["recycle bin"] = Path("shell:RecycleBinFolder")
        known["this pc"] = Path("shell:MyComputerFolder")
    return known


SKIP_DIRS = {"node_modules", ".git", "__pycache__", "appdata", "$recycle.bin", ".venv", "venv", "capricorn-data", ".cache"}


def _score(q: str, name: str) -> float:
    if q in name.lower():
        return max(95.0, match.score(q, name))
    return match.score(q, name)


def _walk(roots: list[str], max_depth: int, want_dirs: bool, q: str, budget_s: float = 2.5):
    t0 = time.time()
    best: tuple[float, float, str] | None = None   # (score, mtime, path)
    for root in roots:
        base_depth = len(Path(root).parts)
        for cur, dirs, files in os.walk(root):
            if time.time() - t0 > budget_s:
                return best
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            if len(Path(cur).parts) - base_depth >= max_depth:
                dirs[:] = []
            for name in (dirs if want_dirs else files):
                stem = name if want_dirs else name.rsplit(".", 1)[0]
                s = _score(q, stem)
                if s >= 85:
                    p = os.path.join(cur, name)
                    try:
                        mt = os.path.getmtime(p)
                    except OSError:
                        mt = 0
                    if best is None or (s, mt) > (best[0], best[1]):
                        best = (s, mt, p)
    return best


def _clean(name: str) -> str:
    n = name.strip().strip("\"'").lower()
    n = re.sub(r"^(the|my)\s+", "", n)
    n = re.sub(r"^(folder|directory)(\s+(of|called|named|for))?\s+", "", n)
    n = re.sub(r"\s+(folder|directory)$", "", n)
    n = re.sub(r"^(the|my)\s+", "", n)
    return n.strip()


def find_folder(name: str, perms: Permissions, aliases: dict[str, str]) -> Path | None:
    raw = name.strip().strip("\"'")
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    if p.is_absolute() and p.is_dir():
        return p
    q = _clean(name)
    for k, v in (aliases or {}).items():
        if k.lower() == q:
            return Path(os.path.expandvars(os.path.expanduser(v)))
    known = _known_folders()
    if q in known:
        return known[q]
    hit = _walk(perms.folder_roots(), max_depth=3, want_dirs=True, q=q)
    return Path(hit[2]) if hit else None


def find_file(name: str, perms: Permissions) -> Path | None:
    raw = name.strip().strip("\"'")
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    if p.is_absolute() and p.is_file():
        return p
    q = _clean(name)
    q = re.sub(r"\s+(file|document|doc|pdf|image|picture|photo|video)$", "", q)
    hit = _walk(perms.folder_roots(), max_depth=4, want_dirs=False, q=q)
    return Path(hit[2]) if hit else None


def _startfile(p: Path) -> None:
    if sys.platform == "win32":
        from . import windows
        windows.allow_foreground()
        os.startfile(str(p))  # type: ignore[attr-defined]
        # bring the new Explorer window / document window to the front
        if p.is_dir() or str(p).lower().startswith("shell:"):
            name = p.name if p.name and not str(p).lower().startswith("shell:") else ""
            m = windows.explorer_folder(name) if name else (lambda w: w.cls == "CabinetWClass")
        else:
            m = windows.title_has(p.stem)
        windows.bring_to_front(m, timeout=8, settle=0.4)
    else:  # dev only
        import subprocess
        subprocess.Popen(["xdg-open", str(p)])


def open_folder(name: str, perms: Permissions, aliases: dict[str, str] | None = None) -> Result:
    folder = find_folder(name, perms, aliases or {})
    if folder is None:
        return Result(False, *persona.line("not_found"))
    is_shell = str(folder).lower().startswith("shell:")
    d = perms.check_folder(folder) if not is_shell else perms.check_folder(Path.home())
    if d.verdict == DENY:
        log_action("open_folder", str(folder), "denied")
        return Result(False, *persona.line("denied", reason=d.reason))

    def run() -> Result:
        try:
            _startfile(folder)
            log_action("open_folder", str(folder), "ok")
            return Result(True, *persona.line("open_folder", name=folder.name or str(folder)))
        except Exception:
            log.exception("open_folder failed")
            return Result(False, *persona.line("error"))

    if d.verdict == ASK:
        return Result(True, "", "surprised", confirm_question=f"Open {folder}?", confirm_run=run, approve=(d.category, d.key))
    return run()


def open_file(name: str, perms: Permissions) -> Result:
    f = find_file(name, perms)
    if f is None:
        return Result(False, *persona.line("not_found"))
    d = perms.check_file(f)
    if d.verdict == DENY:
        log_action("open_file", str(f), "denied")
        return Result(False, *persona.line("denied", reason=d.reason))

    def run() -> Result:
        try:
            _startfile(f)
            log_action("open_file", str(f), "ok")
            return Result(True, *persona.line("open_file", name=f.name))
        except Exception:
            log.exception("open_file failed")
            return Result(False, *persona.line("error"))

    if d.verdict == ASK:
        return Result(True, "", "surprised", confirm_question=f"Open {f.name}?", confirm_run=run, approve=(d.category, d.key))
    return run()
