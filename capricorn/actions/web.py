"""Websites, web search, YouTube and music-in-the-browser."""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import webbrowser
from urllib.parse import quote_plus

from .. import persona
from ..security.permissions import ASK, DENY, Permissions
from .base import Result, log_action

log = logging.getLogger(__name__)

# Spoken site names -> URLs ("open youtube", "open gmail" ...)
KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "youtube music": "https://music.youtube.com",
    "yt music": "https://music.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "calendar": "https://calendar.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "twitch": "https://www.twitch.tv",
    "netflix": "https://www.netflix.com",
    "spotify web": "https://open.spotify.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "linkedin": "https://www.linkedin.com",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://www.wikipedia.org",
    "whatsapp web": "https://web.whatsapp.com",
    "discord web": "https://discord.com/app",
}

MUSIC_SEARCH = {
    "youtube_music": "https://music.youtube.com/search?q={q}",
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "spotify_web": "https://open.spotify.com/search/{q}",
}


REUSE_YOUTUBE_TAB = True   # set from settings (web.reuse_youtube_tab)


def _launch(url: str, perms: Permissions) -> None:
    if REUSE_YOUTUBE_TAB and ("youtube.com/" in url or url.rstrip("/").endswith("youtube.com")):
        from .browser_tab import reuse_tab
        if reuse_tab(url):
            return
    from . import windows
    windows.allow_foreground()
    browser = perms.browser_path()
    if browser:
        subprocess.Popen([browser, url], close_fds=True)
    else:
        webbrowser.open(url, new=2)
    # show the browser (Windows only flashes it in the taskbar when a background app opens a link)
    windows.bring_to_front(windows.browser_window, timeout=6, settle=0.8)


def open_url(url: str, perms: Permissions, line_key: str = "open_url", **fmt) -> Result:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    d = perms.check_url(url)
    if d.verdict == DENY:
        log_action("open_url", url, "denied")
        return Result(False, *persona.line("denied", reason=d.reason))

    def run() -> Result:
        try:
            _launch(url, perms)
            log_action("open_url", url, "ok")
            return Result(True, *persona.line(line_key, **fmt))
        except Exception:
            log.exception("open_url failed")
            return Result(False, *persona.line("error"))

    if d.verdict == ASK:
        return Result(True, "", "surprised", confirm_question=f"Open {url}?", confirm_run=run, approve=(d.category, d.key))
    return run()


def web_search(query: str, perms: Permissions) -> Result:
    return open_url(f"https://www.google.com/search?q={quote_plus(query)}", perms, "web_search")


def youtube_search(query: str, perms: Permissions) -> Result:
    if not query.strip():
        return open_url(KNOWN_SITES["youtube"], perms, "open_youtube")
    return open_url(f"https://www.youtube.com/results?search_query={quote_plus(query)}", perms, "youtube_search")


def _resolve_track(query: str, kind: str = "songs", timeout: float = 7.0) -> dict | None:
    """Find the top YouTube Music result (free, no account) -> {"id", "title", "artist"}.
    kind: "songs" (YouTube Music tracks) or "videos" (regular YouTube videos)."""
    box: dict = {}

    def work() -> None:
        try:
            from ytmusicapi import YTMusic  # type: ignore
            res = YTMusic().search(query, filter=kind, limit=3)
            for r in res:
                if r.get("videoId"):
                    artists = ", ".join(a.get("name", "") for a in (r.get("artists") or []) if a.get("name"))
                    box["hit"] = {"id": r["videoId"], "title": r.get("title") or query, "artist": artists}
                    return
        except Exception as e:  # offline, API change, package missing...
            box["err"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if "err" in box:
        log.warning("track lookup failed: %s", box["err"])
    return box.get("hit")


def _now_playing_line(hit: dict) -> tuple[str, str]:
    title = hit["title"] + (f" by {hit['artist']}" if hit.get("artist") else "")
    return persona.line("music_now", title=title)


# -- what kind of music request is this? ------------------------------------------------------
_LIKED = re.compile(r"\b(liked|likes|favou?rites?|favs?|saved|my (songs|music|tracks|library|playlist))\b", re.I)
_PLAYLISTY = re.compile(r"\b(top|trending|popular|charts?|hits|hottest|viral|playlists?|mix(es)?|radio|station|"
                        r"vibes?|mood|best of|greatest)\b", re.I)
_GENERIC_TAIL = re.compile(r"\b(songs|music|beats|tracks|tunes|bangers|jams|instrumentals?)$", re.I)


def classify_music(query: str) -> str:
    """'liked' (your Liked Music), 'playlist' (top songs, genres, moods, mixes) or 'song'."""
    q = query.strip().lower()
    if not q:
        return "default"
    if _LIKED.search(q):
        return "liked"
    if _PLAYLISTY.search(q) or _GENERIC_TAIL.search(q):
        return "playlist"
    return "song"


def _playlist_query(query: str) -> str:
    q = re.sub(r"\b(play|some|the|a|me)\b", " ", query.lower())
    q = re.sub(r"\btop\s+\d+\b", "top", q)          # "top 10 songs" -> "top songs"
    q = re.sub(r"\s+", " ", q).strip()
    if re.fullmatch(r"(top|trending|popular|hits|top hits|charts?|top songs|trending songs|popular songs|"
                    r"top charts|the charts|hit songs|top tracks|viral songs)", q):
        return "Top 100 Songs Global"
    return q


def _resolve_playlist(query: str, timeout: float = 8.0) -> dict | None:
    """Top YouTube Music playlist for the query -> {"id", "title", "first"} (first = first video id)."""
    box: dict = {}

    def work() -> None:
        try:
            from ytmusicapi import YTMusic  # type: ignore
            yt = YTMusic()
            for kind in ("featured_playlists", "community_playlists", "playlists"):
                try:
                    res = yt.search(query, filter=kind, limit=3)
                except Exception:
                    continue
                for r in res:
                    pid = r.get("browseId") or r.get("playlistId") or ""
                    pid = pid[2:] if pid.startswith("VL") else pid
                    if not pid:
                        continue
                    first = None
                    try:
                        tracks = yt.get_playlist(pid, limit=5).get("tracks") or []
                        first = next((t.get("videoId") for t in tracks if t.get("videoId")), None)
                    except Exception:
                        pass
                    box["hit"] = {"id": pid, "title": r.get("title") or query, "first": first}
                    return
        except Exception as e:
            box["err"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if "err" in box:
        log.warning("playlist lookup failed: %s", box["err"])
    return box.get("hit")


def music_liked(perms: Permissions, service: str = "youtube_music") -> Result:
    """Your Liked Music (uses the account you're signed in with in the browser)."""
    url = {"youtube": "https://www.youtube.com/playlist?list=LL",
           "spotify_web": "https://open.spotify.com/collection/tracks"}.get(service, "https://music.youtube.com/watch?list=LM")
    return open_url(url, perms, "music_liked")


def music_playlist(query: str, perms: Permissions, service: str = "youtube_music") -> Result:
    q = _playlist_query(query)
    if service in ("youtube_music", "youtube"):
        hit = _resolve_playlist(q)
        if hit:
            host = "music.youtube.com" if service == "youtube_music" else "www.youtube.com"
            url = (f"https://{host}/watch?v={hit['first']}&list={hit['id']}" if hit.get("first")
                   else f"https://{host}/playlist?list={hit['id']}")
            r = open_url(url, perms, "music_playlist", title=hit["title"])
            return r
    tmpl = MUSIC_SEARCH.get(service, MUSIC_SEARCH["youtube_music"])
    return open_url(tmpl.format(q=quote_plus(q)), perms, "music_search")


def music_play(query: str, perms: Permissions, service: str = "youtube_music", default: str = "liked") -> Result:
    """Plays what you asked for: your liked music, a playlist (top songs, genre, mood) or a song."""
    base = {"youtube_music": "https://music.youtube.com", "youtube": "https://www.youtube.com",
            "spotify_web": "https://open.spotify.com"}.get(service, "https://music.youtube.com")
    kind = classify_music(query)
    if kind == "default":
        return music_liked(perms, service) if default == "liked" else open_url(base, perms, "music_play")
    if kind == "liked":
        return music_liked(perms, service)
    if kind == "playlist":
        return music_playlist(query, perms, service)
    if service in ("youtube_music", "youtube"):
        hit = _resolve_track(query, "songs")
        if hit:
            host = "music.youtube.com" if service == "youtube_music" else "www.youtube.com"
            r = open_url(f"https://{host}/watch?v={hit['id']}", perms, "music_play")
            if r.ok and not r.confirm_question:
                r.say, r.emotion = _now_playing_line(hit)
            return r
    tmpl = MUSIC_SEARCH.get(service, MUSIC_SEARCH["youtube_music"])
    q = quote_plus(query) if "spotify" not in service else quote_plus(query).replace("+", "%20")
    return open_url(tmpl.format(q=q), perms, "music_search")


def youtube_play(query: str, perms: Permissions) -> Result:
    """'play X on youtube' -> play the top video directly."""
    hit = _resolve_track(query, "videos") or _resolve_track(query, "songs")
    if hit:
        r = open_url(f"https://www.youtube.com/watch?v={hit['id']}", perms, "youtube_search")
        if r.ok and not r.confirm_question:
            r.say, r.emotion = _now_playing_line(hit)
        return r
    return youtube_search(query, perms)


def resolve_site(name: str) -> str | None:
    n = name.lower().strip().removeprefix("the ").strip()
    if n in KNOWN_SITES:
        return KNOWN_SITES[n]
    for suffix in (" website", " site", " dot com", ".com"):
        if n.endswith(suffix):
            base = n[: -len(suffix)].strip()
            if base in KNOWN_SITES:
                return KNOWN_SITES[base]
            if suffix in (" dot com", ".com") and base.replace(" ", "").isalnum():
                return f"https://{base.replace(' ', '')}.com"
    return None
