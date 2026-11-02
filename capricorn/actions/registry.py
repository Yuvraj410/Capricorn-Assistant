"""The ONLY way anything gets executed: a fixed table of named actions.
The LLM can request an action by name; unknown names or bad arguments are rejected."""
from __future__ import annotations

import logging
import re
from typing import Any

from .. import persona
from ..config import Settings
from ..security.permissions import Permissions
from . import apps, files, media, system, web
from .base import Result, log_action

log = logging.getLogger(__name__)


class ActionRegistry:
    def __init__(self, settings: Settings, perms: Permissions) -> None:
        self.settings = settings
        self.perms = perms
        web.REUSE_YOUTUBE_TAB = bool(settings.get("web.reuse_youtube_tab", True))
        self.app_index = apps.AppIndex()
        self.app_index.refresh_async()

    def available(self) -> list[str]:
        """Actions the LLM is told about - only those the permissions don't switch off."""
        p = self.perms
        out = ["time", "ui"]
        if p.mode("web") != "off":
            out += ["open_url", "web_answer", "web_search", "youtube_search", "youtube_play", "music_play", "close_tab",
                    "music_playlist", "music_liked"]
        if p.mode("media_control") != "off":
            out += ["media", "now_playing"]
        if p.mode("apps") != "off":
            out += ["open_app", "close_app", "close_game"]
        if p.mode("folders") != "off":
            out.append("open_folder")
        if p.mode("files") != "off":
            out.append("open_file")
        if p.mode("system") != "off":
            out.append("system")
        return out

    def llm_context(self) -> str:
        """Facts the LLM needs to pick the right action: what's happening on the PC right now
        (media, foreground app, running game) and the exact names of installed games."""
        parts = []
        if self.settings.get("brain.system_context", True):
            try:
                from .. import system_context
                parts.append(system_context.describe(system_context.snapshot(self.app_index)))
            except Exception:
                log.debug("system context failed", exc_info=True)
        games = self.app_index.game_names(60)
        if games and "open_app" in self.available():
            parts.append("INSTALLED GAMES - to launch one use open_app with the EXACT name from this list "
                         "(the user's words may be misheard, pick the closest):\n" + "; ".join(games))
        return "\n\n".join(parts)

    def run(self, name: str, args: dict[str, Any] | None) -> Result:
        args = args if isinstance(args, dict) else {}
        s = lambda k: str(args.get(k) or "").strip()  # noqa: E731
        try:
            if name not in self.available():
                return Result(False, *persona.line("denied", reason="that action is turned off"))
            if name == "open_url":
                return web.open_url(s("url"), self.perms)
            if name == "web_search":
                return web.web_search(s("query"), self.perms)
            if name == "youtube_search":
                return web.youtube_search(s("query"), self.perms)
            if name == "youtube_play":
                return web.youtube_play(s("query"), self.perms)
            svc = self.settings.get("music.service", "youtube_music")
            if name == "music_play":
                return web.music_play(s("query"), self.perms, svc, self.settings.get("music.default", "liked"))
            if name == "music_playlist":
                return web.music_playlist(s("query"), self.perms, svc)
            if name == "music_liked":
                return web.music_liked(self.perms, svc)
            if name == "media":
                return media.media(s("command"), self.perms)
            if name == "now_playing":
                return media.now_playing(self.perms)
            if name == "open_app":
                return apps.open_app(s("name"), self.app_index, self.perms)
            if name == "close_tab":
                from .browser_tab import close_tab
                ok, title = close_tab(s("name"))
                page = re.sub(r" - (Opera|Opera GX|Google Chrome|Microsoft.? Edge|Brave|Vivaldi|Mozilla Firefox)$", "", title)
                if ok:
                    log_action("close_tab", page, "ok")
                    return Result(True, *persona.line("close_tab", name=page or "that tab"))
                return Result(False, *persona.line("close_tab_not_found", name=s("name") or "browser"))
            if name == "close_game":
                from . import close
                return close.close_game(s("name"), self.app_index, self.perms,
                                        ask=bool(self.settings.get("games.ask_before_force_stop", False)))
            if name == "close_app":
                from . import close
                return close.close_app(s("name"), self.app_index, self.perms)
            if name == "open_folder":
                return files.open_folder(s("name") or s("path"), self.perms, self.settings.get("shortcuts.folders", {}))
            if name == "open_file":
                return files.open_file(s("name") or s("path"), self.perms)
            if name == "system":
                return system.system(s("op"), self.perms)
            if name == "time":
                return system.tell_time()
            if name == "ui":
                op = s("op").lower()
                if op not in {"minimal_on", "minimal_off", "show", "hide", "voice_louder", "voice_quieter", "settings"}:
                    return Result(False, *persona.line("not_understood"))
                return Result(True, *persona.line(f"ui_{op}"), data={"ui": op})
        except Exception:
            log.exception("action %s failed", name)
            return Result(False, *persona.line("error"))
        return Result(False, *persona.line("not_understood"))
