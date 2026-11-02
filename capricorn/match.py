"""Name matching for apps, games, folders and files.

Rule of thumb: every meaningful word you said must appear (approximately) in the name.
So "god of war" never matches "Marvel Contest of Champions" (only "of" is shared),
and "bla" never matches "Black Myth: Wukong". Acronyms work: "gta" -> "Grand Theft Auto V".
"""
from __future__ import annotations

import re

try:
    from rapidfuzz import fuzz  # type: ignore
except ImportError:  # pragma: no cover
    fuzz = None

STOPWORDS = {"the", "a", "an", "of", "and", "my", "to", "in", "on", "for", "game", "app", "edition"}
_ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v", "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x"}


def simplify(name: str) -> str:
    n = name.lower().replace("®", "").replace("™", "").replace("&", " and ").replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", n)).strip()


def _ratio(a: str, b: str) -> float:
    if a == b:
        return 100.0
    if fuzz is not None:
        return float(fuzz.ratio(a, b))
    import difflib
    return 100.0 * difflib.SequenceMatcher(None, a, b).ratio()


def _token_ok(q: str, name_tokens: list[str]) -> bool:
    if q.isdigit():   # numbers must match exactly (or as a roman numeral): "2077", "5", "2"
        return q in name_tokens or _ROMAN.get(q) in name_tokens
    for t in name_tokens:
        if t == q or (len(q) >= 4 and t.startswith(q)):
            return True
        if len(q) >= 4 and len(t) >= 4 and _ratio(q, t) >= 85:
            return True
    return False


def score(query: str, name: str) -> float:
    """0 = no match, 100 = exact. Matches only when all meaningful query words are in the name."""
    q, n = simplify(query), simplify(name)
    if not q or not n:
        return 0.0
    if q == n or q.replace(" ", "") == n.replace(" ", ""):      # "chat gpt" == "chatgpt"
        return 100.0
    qc, nc = q.replace(" ", ""), n.replace(" ", "")
    if len(qc) >= 5 and nc.startswith(qc):                     # "wuthering" -> "wutheringwaves"
        return 92.0
    q_tokens = [t for t in q.split() if t not in STOPWORDS] or q.split()
    n_tokens = n.split()
    # acronym: "gta" -> grand theft auto (v), "cs" -> counter strike, "rdr2" -> red dead redemption 2
    initials = "".join(t[0] for t in n_tokens if t not in STOPWORDS and not t.isdigit())
    digits = "".join(t for t in n_tokens if t.isdigit())
    compact = q.replace(" ", "")
    if 2 <= len(compact) <= 6 and compact.isalnum() and len(initials) >= 2:
        letters = re.sub(r"\d", "", compact)
        nums = re.sub(r"\D", "", compact)
        if letters and initials.startswith(letters) and (not nums or nums in digits or _ROMAN.get(nums, "#") in n_tokens):
            return 90.0
    if not all(_token_ok(t, n_tokens) for t in q_tokens):
        # Speech recognisers split/misspell names ("black myth woo kong", "blacksmith wukong"):
        # compare the names with spaces removed.
        nums_ok = all(_token_ok(d, n_tokens) for d in re.findall(r"\d+", q))   # 2078 != 2077
        if len(qc) >= 6 and nums_ok and _ratio(qc, nc) >= 85:
            return 84.0
        return 0.0
    if n.startswith(q):
        return 96.0
    # all words present: prefer names that are mostly what you said (fewer extra words)
    extra = max(0, len([t for t in n_tokens if t not in STOPWORDS]) - len(q_tokens))
    return max(80.0, 95.0 - 3 * extra)


def sounds_like(query: str, name: str) -> float:
    """Looser 0-100 similarity for 'Did you mean ...?' suggestions."""
    qc, nc = simplify(query).replace(" ", ""), simplify(name).replace(" ", "")
    if len(qc) < 5 or not nc:
        return 0.0
    whole = _ratio(qc, nc)
    # also compare against the name without its subtitle / edition words
    core = simplify(re.split(r"[:\-–(]", name)[0]).replace(" ", "")
    return max(whole, _ratio(qc, core) if core else 0.0)


def best(query: str, names: list[str], minimum: float = 80.0) -> int | None:
    """Index of the best matching name, or None."""
    top, idx = 0.0, None
    for i, n in enumerate(names):
        s = score(query, n)
        if s > top or (s == top and idx is not None and len(n) < len(names[idx])):
            top, idx = s, i
    return idx if top >= minimum else None
