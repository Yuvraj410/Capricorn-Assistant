"""'play X' -> game if installed, else the actual song (not a search page)."""
import os, tempfile
from pathlib import Path
os.environ.setdefault("CAPRICORN_HOME", tempfile.mkdtemp())

from capricorn.actions import apps, web
from capricorn.actions.apps import AppEntry, AppIndex
from capricorn.config import Settings, ensure_user_files
from capricorn.security.permissions import Permissions


def fake_steam(tmp: Path) -> Path:
    root = tmp / "Steam"
    (root / "steamapps").mkdir(parents=True)
    lib2 = tmp / "Games" / "SteamLibrary"
    (lib2 / "steamapps").mkdir(parents=True)
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n }\n "1"\n {\n  "path" "%s"\n }\n}\n'
        % (str(root).replace("\\", "\\\\"), str(lib2).replace("\\", "\\\\")))
    def acf(lib, aid, name):
        (lib / "steamapps" / f"appmanifest_{aid}.acf").write_text(f'"AppState"\n{{\n "appid" "{aid}"\n "name" "{name}"\n}}\n')
    acf(root, 489830, "The Elder Scrolls V: Skyrim Special Edition")
    acf(lib2, 1091500, "Cyberpunk 2077")
    acf(lib2, 228980, "Steamworks Common Redistributables")
    acf(root, 367520, "Hollow Knight")
    return root


def test_steam_library_scan(tmp_path):
    games = AppIndex._steam_games(fake_steam(tmp_path))
    names = sorted(g.name for g in games)
    assert names == ["Cyberpunk 2077", "Hollow Knight", "The Elder Scrolls V: Skyrim Special Edition"]
    assert all(g.kind == "steam" and g.is_game for g in games)


def index_with(entries):
    idx = AppIndex()
    idx.entries = entries
    idx._last = 9e18
    return idx


def test_find_game_matching():
    idx = index_with([AppEntry("The Elder Scrolls V: Skyrim Special Edition", "489830", "steam"),
                      AppEntry("Cyberpunk 2077", "1091500", "steam"),
                      AppEntry("Spotify", "Spotify.exe", "appid")])
    assert idx.find_game("skyrim").target == "489830"
    assert idx.find_game("cyberpunk").target == "1091500"
    assert idx.find_game("lofi beats") is None
    assert idx.find_game("spotify") is None          # apps aren't games
    assert idx.find("spotify").name == "Spotify"


def test_router_play_game_vs_song(monkeypatch):
    ensure_user_files("full")
    from capricorn.actions.registry import ActionRegistry
    from capricorn.brain.llm import LLM
    from capricorn.brain.router import Router
    s = Settings()
    reg = ActionRegistry(s, Permissions())
    reg.app_index = index_with([AppEntry("Cyberpunk 2077", "1091500", "steam")])
    launched, opened = [], []
    monkeypatch.setattr(apps, "_launch", lambda e: launched.append(e.target))
    monkeypatch.setattr(web, "_launch", lambda url, perms: opened.append(url))
    monkeypatch.setattr(web, "_resolve_track", lambda q, kind="songs", timeout=7.0:
                        {"id": "abc123", "title": "Shelter", "artist": "Porter Robinson"})
    router = Router(reg, LLM(s))
    r = router.handle("play cyberpunk")
    assert launched == ["1091500"] and r.ok
    r = router.handle("play shelter by porter robinson")
    assert opened == ["https://music.youtube.com/watch?v=abc123"]
    assert "Shelter" in r.say
    r = router.handle("play shelter on youtube")
    assert opened[-1] == "https://www.youtube.com/watch?v=abc123"


def test_music_falls_back_to_search_when_lookup_fails(monkeypatch):
    ensure_user_files("full")
    opened = []
    monkeypatch.setattr(web, "_launch", lambda url, perms: opened.append(url))
    monkeypatch.setattr(web, "_resolve_track", lambda *a, **k: None)
    web.music_play("some obscure song", Permissions())
    assert opened == ["https://music.youtube.com/search?q=some+obscure+song"]


def test_music_intents_route_correctly(monkeypatch):
    ensure_user_files("full")
    from capricorn.actions.registry import ActionRegistry
    from capricorn.brain.llm import LLM
    from capricorn.brain.router import Router
    s = Settings()
    reg = ActionRegistry(s, Permissions())
    reg.app_index = index_with([AppEntry("Marvel Contest of Champions", "3127280", "steam"),
                                AppEntry("Black Myth: Wukong", "2358720", "steam")])
    opened, launched, pl_queries = [], [], []
    monkeypatch.setattr(web, "_launch", lambda url, perms: opened.append(url))
    monkeypatch.setattr(apps, "_launch", lambda e: launched.append(e.name))
    monkeypatch.setattr(web, "_resolve_track", lambda q, kind="songs", timeout=7.0: {"id": "SONG", "title": q, "artist": ""})
    def fake_pl(q, timeout=8.0):
        pl_queries.append(q)
        return {"id": "PLX", "title": "Top 100 Songs Global" if "Top 100" in q else q.title(), "first": "VID1"}
    monkeypatch.setattr(web, "_resolve_playlist", fake_pl)
    router = Router(reg, LLM(s))

    router.handle("play top 10 songs")
    assert pl_queries[-1] == "Top 100 Songs Global"
    assert opened[-1] == "https://music.youtube.com/watch?v=VID1&list=PLX"

    router.handle("play my liked music")
    assert opened[-1] == "https://music.youtube.com/watch?list=LM"
    router.handle("play some songs")
    assert opened[-1] == "https://music.youtube.com/watch?list=LM"

    router.handle("play lofi beats")
    assert pl_queries[-1] == "lofi beats"

    router.handle("play god of war")                 # not installed -> a song, never Marvel
    assert opened[-1] == "https://music.youtube.com/watch?v=SONG" and launched == []
    r = router.handle("play bla-")                    # cut off -> ask again
    assert "again" in r.say.lower() or "one more time" in r.say.lower()
    assert launched == []
    router.handle("play black myth")
    assert launched == ["Black Myth: Wukong"]


def test_misheard_game_offers_did_you_mean(monkeypatch):
    ensure_user_files("full")
    from capricorn.actions.registry import ActionRegistry
    from capricorn.brain.llm import LLM
    from capricorn.brain.router import Router
    s = Settings()
    reg = ActionRegistry(s, Permissions())
    reg.app_index = index_with([AppEntry("Black Myth: Wukong", "2358720", "steam"), AppEntry("Steam", "steam.exe", "appid")])
    launched = []
    monkeypatch.setattr(apps, "_launch", lambda e: launched.append(e.name))
    router = Router(reg, LLM(s))
    router.handle("launch blackmat wukong via steam")          # close enough -> launches directly
    assert launched == ["Black Myth: Wukong"]
    r = router.handle("launched black met who kong")            # unsure -> asks
    assert r.confirm_question == "Did you mean Black Myth: Wukong?"
    r.confirm_run()
    assert launched == ["Black Myth: Wukong"] * 2
    assert "Black Myth: Wukong" in reg.llm_context()
