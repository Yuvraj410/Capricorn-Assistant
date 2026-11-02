"""Turn a chat-bubble reply into something nice to say out loud."""
from __future__ import annotations

import re

_URL = re.compile(r"https?://\S+|www\.\S+")
_ACTION = re.compile(r"\*[^*]{1,40}\*")            # *smirks*
_TAG = re.compile(r"\[[a-z ]{2,20}\]", re.I)       # stray [tags] from the model
_SENT = re.compile(r"(?<=[.!?…])\s+")
# Chatterbox Turbo performs these as real sounds in the cloned voice.
EMOTION_TAGS = {"laughing": "[chuckle]", "sad": "[sigh]"}
# reply emotion -> voice style. A style uses voices/capri-<style>.wav as the reference when that
# recording exists (an angry clip makes angry delivery), otherwise the main capri.wav.
STYLE = {"smile": "happy", "laughing": "playful", "sad": "sad", "surprised": "surprised",
         "angry": "angry", "neutral": "calm", "thinking": "calm"}
STYLES = sorted(set(STYLE.values()))
# Night City slang the voice model mispronounces -> phonetic spelling (speech only, the bubble
# keeps the real word). Add your own in settings.yaml -> voice.pronounce.
PRONOUNCE = {
    "preem": "pream",          # PREEM, rhymes with "dream" (not "prem")
    "preemo": "pream-oh",
    "choomba": "choombuh",     # CHOOM-buh (one word - a hyphen made her pause mid-word)
    "choombas": "choombuhs",
    "av": "A.V.",
    "avs": "A.V.s",
    "bd": "B.D.",
    "bds": "B.D.s",
    "detes": "deets",
}
REPLACE = [
    (re.compile(r"\s*&\s*"), " and "),
    (re.compile(r"\bw/\s*"), "with "),
    (re.compile(r"\be\.g\.", re.I), "for example"),
    (re.compile(r"\bi\.e\.", re.I), "that is"),
    (re.compile(r"\bvs\.?\b", re.I), "versus"),
    (re.compile(r"\bYT\b"), "YouTube"),
]


def respell(text: str, extra: dict | None = None) -> str:
    table = {**PRONOUNCE, **{k.lower(): v for k, v in (extra or {}).items()}}
    def fix(m: re.Match) -> str:
        w = m.group(0)
        rep = table.get(w.lower())
        if rep is None:
            return w
        return rep[0].upper() + rep[1:] if w[0].isupper() and not rep[0].isupper() else rep
    return re.sub(r"[A-Za-z][A-Za-z-]*", fix, text)


def clean(text: str) -> str:
    t = _URL.sub("that link", text)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)        # **bold** keeps its words
    t = _ACTION.sub(" ", t)
    t = _TAG.sub(" ", t)
    t = t.replace("“", '"').replace("”", '"').replace("’", "'").replace("—", ", ").replace("–", ", ")
    t = re.sub(r"[`_#>|~^]", " ", t).replace("*", " ")
    for rx, rep in REPLACE:
        t = rx.sub(rep, t)
    t = "".join(ch for ch in t if ord(ch) < 0x2000 or ch == "…")   # drop emoji / symbols
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.!?;:])", r"\1", t)
    t = re.sub(r",(\s*,)+", ",", t)
    return t.strip(" ,")


def sentences(text: str, min_len: int = 14, max_parts: int = 6) -> list[str]:
    """Split into sentences (each is synthesized separately so speech starts sooner).
    Tiny fragments ("Preem.") are glued to the next sentence so the voice doesn't sound choppy."""
    parts = [p.strip() for p in _SENT.split(text) if p.strip()]
    out: list[str] = []
    carry = ""
    for p in parts:
        cur = f"{carry} {p}".strip() if carry else p
        if len(cur) < min_len:
            carry = cur
            continue
        out.append(cur)
        carry = ""
    if carry:
        if out:
            out[-1] = f"{out[-1]} {carry}"
        else:
            out.append(carry)
    if len(out) > max_parts:
        out = out[:max_parts - 1] + [" ".join(out[max_parts - 1:])]
    return out


def for_speech(text: str, emotion: str = "", tags: bool = True, pronounce: dict | None = None) -> list[str]:
    from .normalize import normalize
    t = respell(normalize(clean(text)), pronounce)
    if not t:
        return []
    parts = sentences(t)
    tag = EMOTION_TAGS.get(emotion) if tags else None
    if tag and parts:
        parts[0] = f"{tag} {parts[0]}"
    return parts
