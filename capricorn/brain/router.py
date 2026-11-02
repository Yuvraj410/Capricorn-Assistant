"""Turns what the user said into a Result: rules first (instant), LLM for everything else."""
from __future__ import annotations

import logging
import re

from .. import persona
from ..actions.base import Result
from ..actions.registry import ActionRegistry
from ..actions import files as files_mod, web as web_mod
from . import rules
from .llm import LLM, BrainOffline

log = logging.getLogger(__name__)


class Router:
    def __init__(self, registry: ActionRegistry, llm: LLM) -> None:
        self.reg = registry
        self.llm = llm

    def handle(self, text: str) -> Result:
        text = (text or "").strip()
        if not text:
            return Result(False, *persona.line("not_understood"))
        parsed = rules.parse(text)
        if parsed:
            intent, args = parsed
            log.info("rule: %s %s", intent, args)
            r = self._run_intent(intent, args)
            if r is not None:
                return r
        return self._ask_llm(text)

    # ------------------------------------------------------------------------------------
    def _run_intent(self, intent: str, args: dict) -> Result | None:
        if intent == "_goodbye":
            return Result(True, *persona.line("goodbye"), data={"dismiss": True})
        if intent == "_thanks":
            return Result(True, *persona.line("thanks"), data={"end": True})
        if intent == "_stop":
            if self.reg.app_index.find_game(args.get("name", "")) and "close_game" in self.reg.available():
                return self.reg.run("close_game", args)
            return None                                  # not a game -> let the LLM interpret it
        if intent == "close_app" and web_mod.resolve_site(args.get("name", "")):
            return self.reg.run("close_tab", {"name": args.get("name", "")})     # "close youtube" = its tab
        if intent == "_ui":
            return self.reg.run("ui", args)
        if intent == "web_answer":
            return self.web_answer(args.get("query", ""))
        if intent == "_unclear":
            return Result(False, *persona.line("unclear"))
        if intent == "_greeting":
            return Result(True, *persona.line("greeting"))
        if intent == "_open":
            return self._open_anything(args.get("name", ""), launch=bool(args.get("launch")))
        if intent == "open_url" and args.get("url") and "." not in args["url"]:
            return None
        if intent == "open_app" and "open_app" in self.reg.available() and not self.reg.app_index.find(args.get("name", "")):
            name = args.get("name", "")
            return (self._did_you_mean(name, games_only=bool(args.get("steam"))) or self._steam_store(name)
                    or Result(False, *persona.line("not_found")))
        if intent == "music_play" and args.get("query") and "open_app" in self.reg.available() \
                and web_mod.classify_music(args["query"]) == "song":
            # "play skyrim" -> launch the game if one is installed with that name
            game = self.reg.app_index.find_game(args["query"])
            if game:
                return self.reg.run("open_app", {"name": game.name})
            maybe = self._did_you_mean(args["query"], games_only=True, minimum=84)
            if maybe:
                maybe.confirm_question = maybe.confirm_question.replace("Did you mean ", "Did you mean the game ")
                return maybe
        return self.reg.run(intent, args)

    def _steam_store(self, name: str) -> Result | None:
        """Not installed? Find it on Steam and open its page (library if owned, else store)."""
        from ..actions import steam
        if "open_app" not in self.reg.available():
            return None
        return steam.open_not_installed(name, self.reg.perms)

    def _open_anything(self, name: str, launch: bool = False) -> Result | None:
        """'open X': website name -> app -> folder -> file. None = let the LLM figure it out."""
        site = web_mod.resolve_site(name)
        avail = self.reg.available()
        if site and "open_url" in avail:
            key = "open_youtube" if "youtube.com" in site and "music" not in site else "open_url"
            return web_mod.open_url(site, self.reg.perms, key)
        if "open_app" in avail and self.reg.app_index.find(name):
            return self.reg.run("open_app", {"name": name})
        aliases = self.reg.settings.get("shortcuts.folders", {}) or {}
        if "open_folder" in avail and files_mod.find_folder(name, self.reg.perms, aliases):
            return self.reg.run("open_folder", {"name": name})
        if "open_file" in avail and files_mod.find_file(name, self.reg.perms):
            return self.reg.run("open_file", {"name": name})
        if "open_app" in avail:
            maybe = self._did_you_mean(name)
            if maybe or not launch:
                return maybe
            return self._steam_store(name)      # "launch X" and X isn't installed -> Steam page
        return None

    def _did_you_mean(self, name: str, games_only: bool = False, minimum: float = 70.0) -> Result | None:
        """Nothing matched exactly (speech recognisers mangle game names) -> offer the closest one."""
        entry = self.reg.app_index.suggest(name, games_only=games_only, minimum=minimum)
        if entry is None:
            return None
        return Result(True, "", "surprised", confirm_question=f"Did you mean {entry.name}?",
                      confirm_run=lambda: self.reg.run("open_app", {"name": entry.name}))

    OFFERABLE = {"web_answer", "web_search", "youtube_search", "youtube_play", "open_url", "music_play", "music_playlist",
                 "music_liked", "open_app", "open_folder", "open_file", "close_app", "close_tab", "close_game"}

    @classmethod
    def _is_offer(cls, say: str, act: dict) -> bool:
        """The reply ends with a question about doing something ("Web search?", "Want me to open it?")."""
        s = say.strip().rstrip("\"' )")
        if act.get("name") not in cls.OFFERABLE or not s.endswith("?"):
            return False
        last = re.split(r"(?<=[.!])\s+", s)[-1].lower()
        return bool(re.search(r"\b(want|should i|shall i|do you|you want|need me|like me|search|open|play|launch|"
                              r"close|look it up|pull it up|google)\b", last)) or len(last.split()) <= 4

    progress = staticmethod(lambda text, emotion="thinking": None)   # set by the app: interim bubble

    def web_answer(self, query: str, question: str = "") -> Result:
        """Search the web, read the results, answer out loud (no browser needed)."""
        from ..actions import research
        query = (query or question).strip()
        if not query:
            return Result(False, *persona.line("unclear"))
        if self.reg.perms.mode("web") == "off":
            return Result(False, *persona.line("denied", reason="web access is turned off"))
        self.progress(*persona.line("web_answer_searching"))
        results = research.search(query)
        if not results:
            return Result(True, "", "sad", confirm_question=persona.line("web_answer_nothing")[0],
                          confirm_run=lambda: self.reg.run("web_search", {"query": query}))
        import datetime as dt
        try:
            out = self.llm.answer_from_results(question or query, research.results_text(results),
                                               dt.date.today().strftime("%A, %B %d, %Y"))
        except BrainOffline:
            return Result(False, *persona.line("brain_offline"))
        srcs = []
        for r in results:
            d = research.domain(r.get("url", ""))
            if d and d not in srcs:
                srcs.append(d)
        log.info("web answer: %r (sources: %s)", out["say"], ", ".join(srcs[:4]))
        return Result(True, out["say"], out["emotion"],
                      data={"sources": [(research.domain(r["url"]), r["url"]) for r in results[:4] if r.get("url")],
                            "caption": "via " + ", ".join(srcs[:3])})

    def _ask_llm(self, text: str) -> Result:
        allowed = self.reg.available()
        try:
            out = self.llm.ask(text, allowed, self.reg.llm_context())
        except BrainOffline as e:
            log.warning("brain offline: %s", e)
            return Result(False, *persona.line("brain_offline"))
        say, emo, act = out["say"], out["emotion"], out["action"]
        log.info("llm: %r %s %s", say, emo, act)
        if not act:
            return Result(True, say, emo)
        if act["name"] == "web_answer":
            q = str(act.get("args", {}).get("query", "")) or text
            if self._is_offer(say, act):
                return Result(True, "", emo or "surprised", confirm_question=say,
                              confirm_run=lambda: self.web_answer(q, text))
            return self.web_answer(q, text)
        if self._is_offer(say, act):
            # "Web search?" + an action = she's OFFERING. Ask first; "sure / go ahead" runs it.
            name, args = act["name"], act.get("args", {})
            return Result(True, "", emo or "surprised", confirm_question=say,
                          confirm_run=lambda: self.reg.run(name, args))
        if act["name"] == "open_app" and not self.reg.app_index.find(str(act.get("args", {}).get("name", ""))):
            alt = self._steam_store(str(act.get("args", {}).get("name", "")))
            if alt is not None:
                return alt
        r = self.reg.run(act["name"], act.get("args", {}))
        if r.confirm_question:
            r.say = say
            return r
        if r.ok:
            # keep the LLM's in-character line, but show useful info from info-actions
            if act["name"] in {"time", "now_playing"}:
                return r
            return Result(True, say, emo, data=r.data)
        return r
