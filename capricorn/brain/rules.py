"""Instant, LLM-free understanding of common commands.

parse() returns (intent, args) or None (= ask the LLM).
Intents are action names from the registry, or special ones starting with "_".
"""
from __future__ import annotations

import re

_FILLER = re.compile(
    r"^(?:(?:please|pls|hey|yo|ok(?:ay)?|so|um+|uh+|now|then|also|and|alright|right|can you|could you|would you|will you|"
    r"i want you to|i want to|i'd like to|i need you to|go ahead and|just)\b[\s,]*)+", re.I)
_TAIL = re.compile(r"[\s,]*(?:please|for me|right now|now|thanks|thank you)\s*$", re.I)

DEVICE = r"(?:the |my |this )?(?:pc|computer|laptop|screen|deck|system|machine)"


def normalize(text: str) -> str:
    t = text.strip().lower()
    t = t.replace("’", "'")
    t = re.sub(r"[.!?]+$", "", t).strip()
    t = _FILLER.sub("", t).strip(" ,")
    for _ in range(2):
        stripped = _TAIL.sub("", t).strip(" ,")
        if stripped:              # "thanks" on its own is a message, not filler
            t = stripped
    return re.sub(r"\s+", " ", t)


_STOP = {"a", "an", "the", "my", "of", "to", "in", "on", "for", "some", "me", "and", "it", "this", "that", "uh", "um"}


def _incomplete(fragment: str) -> bool:
    """A command target that is clearly cut off or empty ('play my', 'open the', 'play bla-')."""
    f = fragment.strip()
    if not f or f.endswith(("-", "—", "...", "…")):
        return True
    words = [w for w in re.findall(r"[a-z0-9']+", f.lower())]
    return not words or all(w in _STOP for w in words) or (len(words) == 1 and len(words[0]) < 3)


def _m(pattern: str, t: str):
    return re.fullmatch(pattern, t, re.I)


def parse(text: str):
    raw = text.strip()
    t = normalize(text)
    if not t:
        return None
    # Whisper marks words it heard cut off with a dash ("play bla-"): don't guess, ask again.
    if raw.endswith(("-", "—")) and len(t.split()) <= 6:
        return ("_unclear", {})

    # -- Capri's look: minimal mode, show / hide ------------------------------------------
    MIN = r"(?:minimal|minimum|mini|stealth|ghost|small)"
    if _m(rf"(?:disable|turn off|exit|leave|stop|quit|end|switch off|close|no more|cancel|get out of)\s+(?:the\s+)?{MIN}(?: mode| look| view)?|"
          rf"{MIN}(?: mode)? off|(?:switch|go|change|come|turn)(?: back)?(?: to| into)?(?: the| your)? (?:normal|full|default|regular|big|full size|old)(?: mode| look| view| self| size)?|"
          r"(?:normal|full|default|regular|big) (?:mode|look|view|size)(?: on| please)?|(?:enable|use|back to) (?:the )?(?:normal|full|default) (?:mode|look)?|"
          r"show (?:your )?full (?:self|body|character)|un ?minimi[sz]e(?: yourself)?|go big|back to normal", t):
        return ("_ui", {"op": "minimal_off"})
    if _m(rf"(?:(?:enable|turn on|switch on|switch to|go to|go into|go|activate|use|start|enter|put yourself in)\s+)?"
          rf"(?:the\s+)?{MIN}(?: mode| look| view)?(?: on| please)?|go (?:minimal|stealth|small|tiny)|be minimal|minimi[sz]e yourself", t):
        return ("_ui", {"op": "minimal_on"})
    if _m(r"(?:hide|stop showing|unshow)\s+(?:yourself|the overlay|your face|capri\w*)|stay hidden|"
          r"(?:don't|do not) (?:show yourself|stay on (?:the )?screen)|(?:disable|turn off) (?:the )?(?:overlay|always (?:visible|on screen))", t):
        return ("_ui", {"op": "hide"})
    if _m(r"(?:show|unhide)\s+(?:yourself|the overlay|your face)|stay on (?:the )?screen|always show yourself|stay visible|"
          r"come back|(?:enable|turn on) (?:the )?(?:overlay|always (?:visible|on screen))|always (?:visible|on screen)(?: on)?", t):
        return ("_ui", {"op": "show"})

    if _m(r"(?:open|show(?: me)?|bring up|pull up|go to)\s+(?:(?:your|capri\w*'?s?) (?:settings|config(?:uration)?|"
          r"control panel|options|preferences)|(?:the |my )?(?:capri\w* )?(?:settings|configuration|preferences))"
          r"(?: screen| page| window| menu)?|settings|configuration", t):
        return ("_ui", {"op": "settings"})
    if _m(r"(?:speak|talk|say it|be)\s+(?:a bit |a little |way )?(?:louder|up)|(?:turn |make )?(?:your(?:self)?|your voice|capri\w*)\s+(?:a bit |a little )?(?:up|louder)|"
          r"(?:i )?(?:can't|cannot|can not) hear you|you(?:'re| are) too (?:quiet|soft)|increase your (?:voice|volume)", t):
        return ("_ui", {"op": "voice_louder"})
    if _m(r"(?:speak|talk|be)\s+(?:a bit |a little )?(?:quieter|softer|lower|down)|(?:turn |make )?(?:your(?:self)?|your voice|capri\w*)\s+(?:a bit |a little )?(?:down|quieter|softer)|"
          r"you(?:'re| are) too loud|lower your (?:voice|volume)|decrease your (?:voice|volume)", t):
        return ("_ui", {"op": "voice_quieter"})

    # -- conversation glue ---------------------------------------------------------------
    if _m(r"(never ?mind|cancel|forget it|nothing|stop listening|go away|bye|goodbye|good night|"
          r"see you|later|that's all|that is all|dismiss|hide)", t):
        return ("_goodbye", {})
    if _m(r"(thanks|thank you|thx|cheers|nice|great|awesome|perfect|cool)( capri| choom)?", t):
        return ("_thanks", {})
    if _m(r"(hi|hello|hey|what's up|whats up|sup|yo|good (morning|afternoon|evening))( capri\w*| there| choom)?", t):
        return ("_greeting", {})

    # -- time ------------------------------------------------------------------------------
    if _m(r"(what('s| is) the )?(time|date|day)( is it)?( now| today)?|what time is it( now)?|"
          r"what('s| is) (today's|todays) date|what day is (it|today)", t):
        return ("time", {})

    # -- media -------------------------------------------------------------------------------
    if _m(r"what('s| is) (playing|this song|the song|this track)( now| right now)?|"
          r"what song is (this|playing)|which song is this|who('s| is) (singing|this)", t):
        return ("now_playing", {})
    MEDIA_NOUN = r"(?:music|song|songs|track|tune|video|playback|audio|player|playlist|spotify|youtube(?: music)?)"
    if _m(rf"(pause|stop|halt|freeze)( (the|this|that|my|current))?( {MEDIA_NOUN}| it| that| this)?", t):
        return ("media", {"command": "pause"})
    if _m(rf"(resume|unpause|continue|play)( (the|this|that|my))?( {MEDIA_NOUN}| it| that)?( again)?|"
          rf"(start|turn)( the)? (music|song) (again|back on)", t):
        return ("media", {"command": "play"})
    # looser: "pause this song which is playing right now", "can you stop the music for a sec"
    if (re.search(r"\b(pause|stop|halt|freeze)\b", t) and not re.search(r"\b(game|app|tab|window|program)\b", t)
            and re.search(rf"\b({MEDIA_NOUN}|playing)\b", t)):
        return ("media", {"command": "pause"})
    if re.match(r"(?:can you |could you |please )?(resume|unpause)\b", t) and not re.search(r"\b(game|download|pdf|doc|file)\b", t):
        return ("media", {"command": "play"})
    if _m(r"(next|skip)( this)?( song| track| one| video)?|play( the)? next( song| track)?", t):
        return ("media", {"command": "next"})
    if _m(r"(previous|last|go back|back)( a| one| to the previous)?( song| track| video)?|play( the)? previous( song| track)?", t):
        return ("media", {"command": "previous"})
    if _m(r"(volume up|turn (it|the volume|the music) up|louder|increase (the )?volume|raise (the )?volume)", t):
        return ("media", {"command": "volume_up"})
    if _m(r"(volume down|turn (it|the volume|the music) down|quieter|lower (the )?volume|decrease (the )?volume)", t):
        return ("media", {"command": "volume_down"})
    if _m(r"(un)?mute( the)?( sound| audio| volume| music)?", t):
        return ("media", {"command": "mute"})

    # -- system ------------------------------------------------------------------------------
    if _m(rf"lock( {DEVICE})?|lock (it|up)", t):
        return ("system", {"op": "lock"})
    if _m(rf"(put {DEVICE} to sleep|sleep mode|go to sleep {DEVICE}|{DEVICE} sleep)", t):
        return ("system", {"op": "sleep"})
    if _m(rf"(shut ?down|turn off|power off|switch off)( {DEVICE})?", t):
        return ("system", {"op": "shutdown"})
    if _m(rf"(restart|reboot)( {DEVICE})?", t):
        return ("system", {"op": "restart"})

    # -- closing games / apps -------------------------------------------------------------------
    if _m(r"(?:close|quit|exit|stop(?: playing)?|kill|end|terminate|shut down)\s+(?:the |this |my |current )?game", t):
        return ("close_game", {"name": ""})
    m = _m(r"(?:close|quit|exit|kill|end|terminate|stop playing|stop running|shut down|close down)\s+"
           r"(?:the |my |this )?(?P<x>.+?)(?:\s+(?:game|app|application|window|program))?", t)
    if m and not re.fullmatch(r"(it|that|this|everything|all|yourself|capri\w*)", m.group("x")):
        x = m.group("x").strip()
        if _incomplete(x):
            return ("_unclear", {})
        tab = re.fullmatch(r"(?:(?:this|that|current|the|my|active)\s+)?(?P<site>.*?)\s*tab", x)
        if tab:
            site = re.sub(r"^(this|that|current|the|my|active)\s+", "", tab.group("site")).strip()
            return ("close_tab", {"name": site})
        return ("close_app", {"name": x})
    m = _m(r"stop\s+(?:the |my )?(?P<x>.+?)(?:\s+game)?", t)
    if m and not _incomplete(m.group("x")):
        return ("_stop", {"name": m.group("x")})      # router: only if it's an installed game

    # -- music / youtube / search ---------------------------------------------------------------
    m = _m(r"(?:play|launch(?:ed)?|start(?:ed)?|open(?:ed)?|run|boot up)\s+(?P<q>.+?)\s+(?:on|in|from|through|via|using|with) steam", t)
    if m:
        return ("open_app", {"name": m.group("q"), "steam": True})
    m = _m(r"(?:play|put on|queue( up)?|start playing)\s+(?P<q>.+?)\s+on (?:youtube|you tube)(?! music)", t)
    if m:
        return ("youtube_play", {"query": m.group("q")})
    m = _m(r"(?:play|launch|start|boot up)\s+(?:the\s+)?game\s+(?P<q>.+)|(?:play|launch|start)\s+(?P<q2>.+?)\s+game", t)
    if m:
        return ("open_app", {"name": m.group("q") or m.group("q2"), "steam": True})
    m = _m(r"(?:play|put on|queue(?: up)?|start playing)\s+(?:some\s+)?(?P<q>.+?)(?:\s+on (?:youtube music|yt music|spotify|music))?", t)
    if m and m.group("q") not in {"music", "song", "songs", "it", "the music", "something"}:
        if _incomplete(m.group("q")):
            return ("_unclear", {})
        return ("music_play", {"query": m.group("q")})
    if _m(r"(play|put on)( some)? (music|songs?|something)", t):
        return ("music_play", {"query": ""})
    m = _m(r"(?:search|look up|find)\s+(?:on\s+)?(?:youtube|you tube)\s+(?:for\s+)?(?P<q>.+)|"
           r"(?:search|look up|find)\s+(?P<q2>.+?)\s+on (?:youtube|you tube)|youtube\s+(?P<q3>.+)", t)
    if m:
        return ("youtube_search", {"query": m.group("q") or m.group("q2") or m.group("q3")})
    # "google X" / "search X on google" / "open a search for X" -> open the results page
    m = _m(r"(?:google|search on google(?: for)?|open a (?:google )?search for|search google for)\s+(?P<q>.+?)|"
           r"search(?: for)?\s+(?P<q2>.+?)\s+on (?:google|the browser|bing)", t)
    if m and (m.group("q") or m.group("q2")):
        return ("web_search", {"query": m.group("q") or m.group("q2")})
    # "look up X", "search for X", "find out X", "what's the latest on X" -> Capri reads the results and answers
    m = _m(r"(?:look up|search(?: the (?:web|net|internet))?(?: for)?|find out|research|dig up|"
           r"what(?:'s| is) the latest (?:on|about|with)|any news (?:on|about))\s+(?P<q>.+?)"
           r"(?:\s+(?:and|then)\s+(?:tell|let)\s+me.*)?(?:\s+(?:online|on the (?:web|net|internet)))?", t)
    if m:
        return ("web_answer", {"query": m.group("q")})

    # -- open things ------------------------------------------------------------------------------
    m = _m(r"(?P<verb>open|launch|launched|start|run|fire up|boot up|load|go to|show me|show|bring up|pull up)\s+(?:up\s+)?(?P<x>.+)", t)
    if m:
        x = m.group("x").strip()
        verb = m.group("verb")
        if _incomplete(x):
            return ("_unclear", {})
        fm = re.fullmatch(r"(?:the |my |a )?(?:folder|directory)(?:\s+(?:of|called|named|for|with))?\s+(?P<f>.+)", x)
        if fm:
            return ("open_folder", {"name": fm.group("f")})
        if re.search(r"\b(folder|directory)$", x):
            return ("open_folder", {"name": x})
        if re.search(r"\b(file|document|pdf|doc|image|picture|photo|video|spreadsheet)$", x) or \
                re.search(r"\.[a-z0-9]{2,4}$", x) and not re.search(r"\.(com|org|net|io|ai|gg|tv|dev|app)$", x):
            return ("open_file", {"name": x})
        if x.startswith(("http://", "https://", "www.")) or re.search(r"\.(com|org|net|io|ai|gg|tv|dev|app)$", x):
            return ("open_url", {"url": x})
        if verb in {"launch", "launched", "start", "run", "fire up", "boot up"}:
            return ("_open", {"name": x, "launch": True})
        return ("_open", {"name": x})
    return None
