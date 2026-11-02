"""Local LLM via Ollama's HTTP API (free, offline). Returns validated {say, emotion, action}."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from .. import persona
from ..config import Settings

log = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "properties": {
        "say": {"type": "string"},
        "emotion": {"type": "string", "enum": persona.EMOTIONS},
        "action": {
            "anyOf": [
                {"type": "null"},
                {"type": "object",
                 "properties": {"name": {"type": "string"}, "args": {"type": "object"}},
                 "required": ["name"]},
            ]
        },
    },
    "required": ["say", "emotion", "action"],
}


class BrainOffline(Exception):
    pass


class LLM:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.history: list[dict[str, str]] = []
        self._think_supported = True

    @property
    def url(self) -> str:
        return str(self.s.get("brain.ollama_url", "http://127.0.0.1:11434")).rstrip("/")

    def status(self) -> tuple[bool, str]:
        """(ok, message) - is Ollama up and is the model pulled?"""
        model = self.s.get("brain.model", "qwen3:4b")
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=3)
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
            base = model if ":" in model else model + ":latest"
            if model in names or base in names:
                return True, "ok"
            return False, f"model {model} not pulled (run: ollama pull {model})"
        except requests.RequestException as e:
            return False, f"Ollama not reachable at {self.url} ({e.__class__.__name__})"

    def models(self) -> list[str]:
        """Models already pulled in Ollama (for the settings screen)."""
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=2)
            return sorted(m.get("name", "") for m in r.json().get("models", []) if m.get("name"))
        except Exception:
            return []

    def warm_up(self) -> None:
        """Load the model into memory in the background so the first reply is fast."""
        try:
            requests.post(f"{self.url}/api/generate",
                          json={"model": self.s.get("brain.model"), "prompt": "", "keep_alive": self.s.get("brain.keep_alive", "5m")},
                          timeout=120)
        except requests.RequestException:
            pass

    def ask(self, user_text: str, allowed_actions: list[str], context: str = "") -> dict[str, Any]:
        out = self._ask(user_text, allowed_actions, context)
        last = next((m["content"] for m in reversed(self.history[:-2]) if m["role"] == "assistant"), None)
        if last and json.loads(last).get("say") == out["say"]:
            # The model is stuck repeating itself. Retry WITH the conversation (dropping it lost the
            # thread - "sure, go ahead" then meant nothing) plus an explicit nudge.
            log.info("LLM repeated itself - retrying with a nudge")
            self.history = self.history[:-2]
            nudge = ("(You just said exactly that. Don't repeat yourself. If the user is agreeing to "
                     "something you offered, do it now with the action.)")
            out = self._ask(user_text, allowed_actions, context, nudge=nudge)
        return out

    def _ask(self, user_text: str, allowed_actions: list[str], context: str, nudge: str = "") -> dict[str, Any]:
        sys_prompt = persona.build_system_prompt(allowed_actions, context, self.s)
        if nudge:
            sys_prompt += "\n" + nudge
        n = int(self.s.get("brain.history_turns", 10)) * 2
        messages = [{"role": "system", "content": sys_prompt}] + self.history[-n:] + \
                   [{"role": "user", "content": user_text}]
        body: dict[str, Any] = {
            "model": self.s.get("brain.model", "qwen3:4b"),
            "messages": messages,
            "stream": False,
            "format": SCHEMA,
            "keep_alive": self.s.get("brain.keep_alive", "5m"),
            "options": {"temperature": float(self.s.get("brain.temperature", 0.8)), "num_ctx": 4096,
                        "repeat_penalty": 1.15},
        }
        if self._think_supported:
            body["think"] = False
        timeout = float(self.s.get("brain.timeout", 60))
        try:
            r = requests.post(f"{self.url}/api/chat", json=body, timeout=timeout)
            if r.status_code == 400 and "think" in r.text.lower() and "think" in body:
                self._think_supported = False
                body.pop("think")
                r = requests.post(f"{self.url}/api/chat", json=body, timeout=timeout)
            r.raise_for_status()
        except requests.RequestException as e:
            raise BrainOffline(str(e)) from e
        content = r.json().get("message", {}).get("content", "")
        out = self._parse(content, allowed_actions)
        self.history += [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)}]
        self.history = self.history[-40:]
        return out

    @staticmethod
    def _parse(content: str, allowed: list[str]) -> dict[str, Any]:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
        data: Any = None
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.S)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    data = None
        if not isinstance(data, dict):
            return {"say": content[:300] or "...", "emotion": "neutral", "action": None}
        say = str(data.get("say") or "").strip() or "..."
        emo = str(data.get("emotion") or "neutral").lower()
        if emo not in persona.EMOTIONS:
            emo = "neutral"
        act = data.get("action")
        if isinstance(act, dict) and act.get("name") in allowed:
            act = {"name": act["name"], "args": act.get("args") if isinstance(act.get("args"), dict) else {}}
        else:
            act = None
        return {"say": say, "emotion": emo, "action": act}

    def answer_from_results(self, question: str, results_text: str, today: str = "") -> dict[str, Any]:
        """Read web search results and answer like Capri. Added to the conversation, so follow-ups
        ("what about the Nasdaq?") still make sense."""
        sys_prompt = persona.build_system_prompt([], "", self.s).split("ACTIONS")[0] + (
            "\nYOU JUST SEARCHED THE WEB. Answer the user's question using ONLY these results. "
            "Give the actual answer (numbers, names, dates) in 2-3 short sentences, up to ~55 words. "
            "If the results are old or don't answer it, say so honestly. Never invent figures. "
            f"Today is {today}.\n\nSEARCH RESULTS:\n{results_text}\n\n"
            'Respond with ONLY JSON: {"say": "...", "emotion": "neutral|smile|surprised|sad|thinking"}')
        body: dict[str, Any] = {
            "model": self.s.get("brain.model", "qwen3:4b"),
            "messages": [{"role": "system", "content": sys_prompt}] + self.history[-6:] +
                        [{"role": "user", "content": question}],
            "stream": False, "format": "json", "keep_alive": self.s.get("brain.keep_alive", "5m"),
            "options": {"temperature": 0.4, "num_ctx": 6144},
        }
        if self._think_supported:
            body["think"] = False
        try:
            r = requests.post(f"{self.url}/api/chat", json=body, timeout=float(self.s.get("brain.timeout", 60)))
            r.raise_for_status()
        except requests.RequestException as e:
            raise BrainOffline(str(e)) from e
        out = self._parse(r.json().get("message", {}).get("content", ""), [])
        self.history += [{"role": "user", "content": question},
                         {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)}]
        self.history = self.history[-40:]
        return out

    def reset(self) -> None:
        self.history.clear()
