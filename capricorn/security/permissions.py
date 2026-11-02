"""Permission checks. Every action asks this module before touching the system.

Decisions:  ALLOW  - go ahead
            ASK    - ask the user to confirm first
            DENY   - refuse (with a reason Capri can say)
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yaml

from .. import paths

log = logging.getLogger(__name__)

ALLOW, ASK, DENY = "allow", "ask", "deny"

# Power actions always need confirmation, regardless of the file.
ALWAYS_CONFIRM_SYSTEM = {"sleep", "shutdown", "restart"}

HARD_BLOCKED_EXT = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".msp", ".scr", ".reg", ".hta", ".cpl", ".jar", ".psm1", ".psd1", ".sys", ".dll",
}


@dataclass
class Decision:
    verdict: str
    reason: str = ""
    category: str = ""      # set on ASK so a "yes" can be remembered
    key: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict == ALLOW


def _norm_path(p: str | os.PathLike) -> str:
    s = os.path.expandvars(os.path.expanduser(str(p)))
    try:
        s = str(Path(s).resolve(strict=False))
    except OSError:
        pass
    return os.path.normcase(os.path.normpath(s))


def _is_under(child: str, parent: str) -> bool:
    child, parent = _norm_path(child), _norm_path(parent)
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:  # different drives
        return False


def _domain_match(host: str, pattern: str) -> bool:
    host, pattern = host.lower().strip("."), pattern.lower().strip(".")
    if pattern.startswith("*."):
        pattern = pattern[2:]
    return host == pattern or host.endswith("." + pattern)


class Permissions:
    def __init__(self, file: Path | None = None) -> None:
        self.file = file or (paths.user_dir() / paths.PERMISSIONS_FILE)
        self._lock = threading.Lock()
        self.approvals: dict[str, set[str]] = {}
        self.reload()

    # -- remembered approvals ------------------------------------------------------------
    # A "yes" to a confirmation is saved in capricorn-data/approvals.json, so Capri doesn't ask
    # again for the same app / folder / file / website. Power actions are never remembered.
    def _approvals_file(self) -> Path:
        return self.file.parent / "approvals.json"

    def _load_approvals(self) -> None:
        try:
            data = json.loads(self._approvals_file().read_text(encoding="utf-8"))
            self.approvals = {k: set(v) for k, v in data.items() if isinstance(v, list)}
        except (OSError, ValueError):
            self.approvals = {}

    def remember(self, category: str, key: str) -> bool:
        if not category or not key or (category == "system" and key in ALWAYS_CONFIRM_SYSTEM):
            return False
        with self._lock:
            self.approvals.setdefault(category, set()).add(key)
            try:
                self._approvals_file().write_text(
                    json.dumps({k: sorted(v) for k, v in self.approvals.items()}, indent=2), encoding="utf-8")
            except OSError:
                log.exception("could not save approvals")
        log.info("remembered approval: %s %s", category, key)
        return True

    def forget_approvals(self) -> None:
        with self._lock:
            self.approvals = {}
            try:
                self._approvals_file().unlink(missing_ok=True)
            except OSError:
                pass

    def _finalize(self, d: Decision, category: str, key: str) -> Decision:
        if d.verdict != ASK:
            return d
        if key in self.approvals.get(category, set()) and not (category == "system" and key in ALWAYS_CONFIRM_SYSTEM):
            return Decision(ALLOW)
        d.category, d.key = category, key
        return d

    def check_app(self, app_name: str) -> Decision:
        return self._finalize(self._check_app(app_name), "apps", app_name.lower().strip())

    def check_folder(self, folder) -> Decision:
        return self._finalize(self._check_folder(folder), "folders", _norm_path(folder))

    def check_file(self, file) -> Decision:
        return self._finalize(self._check_file(file), "files", _norm_path(file))

    def check_url(self, url: str) -> Decision:
        host = (urlparse(url).hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        return self._finalize(self._check_url(url), "web", host)

    def check_media(self) -> Decision:
        return self._finalize(self._check_media(), "media", "media")

    def check_system(self, op: str) -> Decision:
        return self._finalize(self._check_system(op), "system", op)

    def reload(self) -> None:
        self._load_approvals()
        try:
            with open(self.file, encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            with open(paths.DEFAULTS_DIR / "permissions.safe.yaml", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            log.error("permissions.yaml is invalid (%s) - everything set to 'ask'", e)
            self.data = {}

    # -- helpers ---------------------------------------------------------------
    def _section(self, name: str) -> dict:
        sec = self.data.get(name) or {}
        return sec if isinstance(sec, dict) else {}

    def _mode(self, name: str) -> str:
        mode = str(self._section(name).get("mode", "ask")).lower().strip()
        return mode if mode in {"all", "allowlist", "ask", "off"} else "ask"

    def mode(self, name: str) -> str:
        return self._mode(name)

    # -- categories --------------------------------------------------------------
    def _check_app(self, app_name: str) -> Decision:
        sec, mode = self._section("apps"), self._mode("apps")
        name = app_name.lower()
        if any(d.lower() in name for d in sec.get("deny", []) or []):
            return Decision(DENY, f"{app_name} is on your blocked apps list")
        if mode == "off":
            return Decision(DENY, "opening apps is turned off in your permissions")
        if mode == "all":
            return Decision(ALLOW)
        listed = any(a.lower() in name or name in a.lower() for a in sec.get("allow", []) or [])
        if mode == "allowlist":
            return Decision(ALLOW) if listed else Decision(DENY, f"{app_name} isn't on your allowed apps list")
        return Decision(ALLOW) if listed else Decision(ASK, f"open {app_name}")

    def _check_folder(self, folder: str | os.PathLike) -> Decision:
        sec, mode = self._section("folders"), self._mode("folders")
        for d in sec.get("deny", []) or []:
            if _is_under(folder, d):
                return Decision(DENY, "that folder is blocked in your permissions")
        if mode == "off":
            return Decision(DENY, "opening folders is turned off in your permissions")
        if mode == "all":
            return Decision(ALLOW)
        listed = any(_is_under(folder, a) for a in sec.get("allow", []) or [])
        if mode == "allowlist":
            return Decision(ALLOW) if listed else Decision(DENY, "that folder isn't in your allowed folders")
        return Decision(ALLOW) if listed else Decision(ASK, f"open the folder {Path(folder).name}")

    def _check_file(self, file: str | os.PathLike) -> Decision:
        sec, mode = self._section("files"), self._mode("files")
        ext = Path(file).suffix.lower()
        blocked = HARD_BLOCKED_EXT | {e.lower() for e in sec.get("blocked_extensions", []) or []}
        if ext in blocked:
            return Decision(DENY, f"I don't open {ext} files - they'd run code")
        if mode == "off":
            return Decision(DENY, "opening files is turned off in your permissions")
        folder_d = self._check_folder(Path(file).parent)
        if folder_d.verdict == DENY:
            return folder_d
        if mode == "all":
            return folder_d if folder_d.verdict == ASK else Decision(ALLOW)
        if mode == "allowlist":
            return Decision(ALLOW) if folder_d.verdict == ALLOW else Decision(DENY, "that file isn't in an allowed folder")
        return Decision(ASK, f"open {Path(file).name}")

    def _check_url(self, url: str) -> Decision:
        sec, mode = self._section("web"), self._mode("web")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return Decision(DENY, "I only open http and https links")
        host = parsed.hostname or ""
        if any(_domain_match(host, d) for d in sec.get("deny_domains", []) or []):
            return Decision(DENY, f"{host} is blocked in your permissions")
        if mode == "off":
            return Decision(DENY, "opening websites is turned off in your permissions")
        if mode == "all":
            return Decision(ALLOW)
        listed = any(_domain_match(host, d) for d in sec.get("allow_domains", []) or [])
        if mode == "allowlist":
            return Decision(ALLOW) if listed else Decision(DENY, f"{host} isn't on your allowed sites")
        return Decision(ALLOW) if listed else Decision(ASK, f"open {host}")

    def _check_media(self) -> Decision:
        mode = self._mode("media_control")
        if mode == "off":
            return Decision(DENY, "media controls are turned off in your permissions")
        if mode == "ask":
            return Decision(ASK, "control your media")
        return Decision(ALLOW)

    def _check_system(self, op: str) -> Decision:
        sec, mode = self._section("system"), self._mode("system")
        allowed_ops = {str(o).lower() for o in sec.get("allow", []) or []}
        if mode == "off":
            return Decision(DENY, "system actions are turned off in your permissions")
        if mode in {"allowlist", "ask"} and op not in allowed_ops:
            if mode == "allowlist":
                return Decision(DENY, f"{op} isn't allowed in your permissions")
            return Decision(ASK, op)
        if op in ALWAYS_CONFIRM_SYSTEM:
            return Decision(ASK, op)
        return Decision(ALLOW)

    # -- browser -------------------------------------------------------------------
    def browser_path(self) -> str | None:
        sec = self._section("browser")
        if str(sec.get("use", "system_default")).lower() == "custom":
            p = os.path.expandvars(os.path.expanduser(str(sec.get("custom_path") or "")))
            if p and Path(p).exists():
                return p
            log.warning("Custom browser path not found (%s) - using system default", p)
        return None

    def folder_roots(self) -> list[str]:
        """Folders to search when looking for a file/folder by name."""
        sec = self._section("folders")
        roots = sec.get("allow") or []
        if not roots or self._mode("folders") == "all":
            roots = list(roots) + ["~/Desktop", "~/Documents", "~/Downloads", "~/Pictures",
                                   "~/Music", "~/Videos", "~/OneDrive/Desktop", "~/OneDrive/Documents"]
        out, seen = [], set()
        for r in roots:
            n = _norm_path(r)
            if n not in seen and os.path.isdir(n):
                seen.add(n)
                out.append(n)
        return out
