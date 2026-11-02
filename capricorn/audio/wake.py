"""Wake-word matching on transcripts ("hey capri, open youtube" -> "open youtube")."""
from __future__ import annotations

import re

try:
    from rapidfuzz import fuzz  # type: ignore
except ImportError:  # pragma: no cover
    fuzz = None

PREFIXES = {"hey", "hi", "hello", "okay", "ok", "yo", "oi", "a", "ay", "hay", "heya", "hej"}
CALL_PREFIXES = {"hey", "hi", "hello", "okay", "ok", "yo", "oi", "hay", "heya", "hej", "ay"}
# After a bare short wake word ("C, open youtube") the next word must look like a command.
COMMAND_STARTERS = {
    "open", "launch", "start", "run", "play", "pause", "resume", "stop", "close", "quit", "exit", "kill",
    "next", "skip", "previous", "back", "volume", "louder", "quieter", "mute", "unmute", "search", "google",
    "look", "find", "show", "hide", "lock", "turn", "go", "switch", "enable", "disable", "minimal", "normal",
    "what", "what's", "whats", "who", "how", "when", "where", "why", "tell", "set", "put", "queue", "bring",
    "pull", "fire", "boot", "load", "can", "could", "would", "please", "shut", "restart", "thanks", "thank",
}
# How Whisper tends to write a spoken "Hey C": "Hey, Siri", "Hey, see.", "Hey Cee", "AC", "HC".
SHORT_VARIANTS = {"siri", "cee", "see", "sea", "si", "c"}
MERGED_CALLS = {"ac", "hc", "heyc", "heycee", "heysee", "haycee", "heyce"}
NOT_A_CALL = {"you", "ya", "yah", "u", "plus", "sharp", "programming", "language", "code", "drive", "grade", "minus"}
_TOKEN = re.compile(r"[a-z']+")


def _sim(a: str, b: str) -> float:
    if a == b:
        return 100.0
    if fuzz is None:
        import difflib
        return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()
    return float(fuzz.ratio(a, b))


class WakeMatcher:
    def __init__(self, words: list[str], aliases: list[str] | None = None, threshold: float = 80.0,
                 short_forms: list[str] | None = None) -> None:
        forms = [w.lower().strip() for w in (words or []) + (aliases or []) if w and w.strip()]
        self.forms = sorted(set(forms), key=len, reverse=True)
        self.compact = {f.replace(" ", "") for f in self.forms}
        self.threshold = threshold
        # Very short wake words ("C" = "see" / "sea" / "si") - matched exactly, with extra rules.
        self.short = {s.lower().strip(" .") for s in (short_forms or []) if s and s.strip(" .")}

    def vosk_vocab(self) -> list[str]:
        """Single words for the Vosk grammar (out-of-vocabulary ones are ignored by Vosk)."""
        toks = set()
        for f in self.forms:
            first = f.split()[0]           # "capri con" -> "capri"; never feed "con"/"corn" alone
            if len(first) >= 5:
                toks.add(first)
        return sorted(toks | self.short | {"hey", "okay"})

    def _find_short(self, text: str, spans) -> tuple[bool, str] | None:
        """'Hey C ...' anywhere at the start, or 'C, <command>' as the very first word."""
        if not self.short:
            return None
        toks = [t for t, _, _ in spans]
        if toks[0] in MERGED_CALLS and (len(toks) == 1 or toks[1] not in NOT_A_CALL):
            return True, text[spans[0][2]:].lstrip(" ,.!?:;-—").strip()
        for i, tok in enumerate(toks[:3]):
            if tok not in self.short and not (i > 0 and tok in SHORT_VARIANTS):
                continue
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            called = i > 0 and toks[i - 1] in CALL_PREFIXES and all(t in CALL_PREFIXES for t in toks[:i])
            first_with_command = i == 0 and nxt in COMMAND_STARTERS
            if nxt in NOT_A_CALL:
                return None
            if called or first_with_command:
                rest = text[spans[i][2]:].lstrip(" ,.!?:;-—")
                return True, rest.strip()
        return None

    def find(self, text: str, search_tokens: int = 4) -> tuple[bool, str]:
        """Is there a wake word in the first few words? Returns (found, text after the wake word)."""
        low = text.lower().replace("’", "'")
        spans = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(low)]
        if not spans:
            return False, ""
        short = self._find_short(text, spans)
        if short:
            return short
        limit = min(len(spans), search_tokens)
        best: tuple[float, int] | None = None   # (score, end index in spans)
        for i in range(limit):
            for n in (1, 2, 3):              # "capri", "capri con", "cap ri corn"
                if i + n > len(spans):
                    break
                cand = "".join(t for t, _, _ in spans[i:i + n])
                if len(cand) < 4:
                    continue
                score = max(_sim(cand, f) for f in self.compact)
                if score >= self.threshold and (best is None or (score, i + n - 1) > best):
                    best = (score, i + n - 1)
            if best and best[0] >= 99:
                break
        if best is None:
            return False, ""
        end_char = spans[best[1]][2]
        rest = text[end_char:].lstrip(" ,.!?:;-—")
        return True, rest.strip()

    def contains(self, text: str) -> bool:
        return self.find(text, search_tokens=12)[0]
