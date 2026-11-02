"""Steam: installed -> library page then launch; not installed -> library/store page + 'install first'."""
import os, tempfile, time
from pathlib import Path
os.environ.setdefault("CAPRICORN_HOME", tempfile.mkdtemp())

from capricorn.actions import apps, steam, windows
from capricorn.actions.apps import AppEntry, AppIndex
from capricorn.config import Settings, ensure_user_files
from capricorn.security.permissions import Permissions

LOCALCONFIG = '''"UserLocalConfigStore"
{
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"apps"
				{
					"1245620"
					{
						"LastPlayed"		"1700000000"
					}
					"2358720"
					{
						"Playtime"		"900"
					}
				}
			}
		}
	}
}
'''


def test_owned_appids(tmp_path):
    cfg = tmp_path / "userdata" / "123" / "config"
    cfg.mkdir(parents=True)
    (cfg / "localconfig.vdf").write_text(LOCALCONFIG)
    steam._owned_cache = (0.0, set())
    assert steam.owned_appids(tmp_path) == {"1245620", "2358720"}


def test_best_store_match():
    res = [("1245620", "ELDEN RING"), ("2778580", "ELDEN RING NIGHTREIGN"), ("123", "Elden Ring Soundtrack")]
    assert steam.best_store_match("elden ring", res)[0] == "1245620"
    assert steam.best_store_match("god of war", res) is None


def test_launch_installed_shows_library_then_launches(monkeypatch):
    opened = []
    monkeypatch.setattr(steam, "_open", lambda url: opened.append(url))
    monkeypatch.setattr(windows, "bring_to_front", lambda *a, **k: None)
    monkeypatch.setattr(steam.time, "sleep", lambda s: None)
    steam.launch_installed("2358720", "Black Myth: Wukong")
    for _ in range(50):
        if len(opened) == 2:
            break
        time.sleep(0.02)
    assert opened == ["steam://nav/games/details/2358720", "steam://rungameid/2358720"]


def _router(monkeypatch, entries):
    ensure_user_files("full")
    from capricorn.actions.registry import ActionRegistry
    from capricorn.brain.llm import LLM
    from capricorn.brain.router import Router
    s = Settings()
    reg = ActionRegistry(s, Permissions())
    idx = AppIndex(); idx.entries = entries; idx._last = 9e18
    reg.app_index = idx
    return Router(reg, LLM(s))


def test_not_installed_owned_opens_library_page(monkeypatch):
    opened = []
    monkeypatch.setattr(steam, "available", lambda: True)
    monkeypatch.setattr(steam, "store_search", lambda name, timeout=6.0: [("1245620", "ELDEN RING")])
    monkeypatch.setattr(steam, "owned_appids", lambda root=None: {"1245620"})
    monkeypatch.setattr(steam, "_open", lambda url: opened.append(url))
    monkeypatch.setattr(steam, "_show_steam", lambda delay=0.0: None)
    r = _router(monkeypatch, [AppEntry("Black Myth: Wukong", "2358720", "steam")]).handle("launch elden ring")
    assert opened == ["steam://nav/games/details/1245620"]
    assert "install" in r.say.lower() and "ELDEN RING" in r.say


def test_not_owned_opens_store_page(monkeypatch):
    opened = []
    monkeypatch.setattr(steam, "available", lambda: True)
    monkeypatch.setattr(steam, "store_search", lambda name, timeout=6.0: [("1245620", "ELDEN RING")])
    monkeypatch.setattr(steam, "owned_appids", lambda root=None: set())
    monkeypatch.setattr(steam, "_open", lambda url: opened.append(url))
    monkeypatch.setattr(steam, "_show_steam", lambda delay=0.0: None)
    r = _router(monkeypatch, []).handle("play elden ring on steam")
    assert opened == ["steam://store/1245620"] and "store" in r.say.lower()


def test_installed_game_uses_library_flow(monkeypatch):
    calls = []
    monkeypatch.setattr(steam, "launch_installed", lambda appid, name: calls.append((appid, name)))
    r = _router(monkeypatch, [AppEntry("Black Myth: Wukong", "2358720", "steam")]).handle("launch black myth wukong")
    assert calls == [("2358720", "Black Myth: Wukong")] and "library" in r.say.lower()


def test_plain_open_does_not_hit_the_store(monkeypatch):
    monkeypatch.setattr(steam, "available", lambda: True)
    called = []
    monkeypatch.setattr(steam, "store_search", lambda name, timeout=6.0: called.append(name) or [])
    r = _router(monkeypatch, []).handle("open my notes thing")
    assert called == []


def test_window_matchers():
    w = windows.Win(1, "Steam", "steamwebhelper.exe", "SDL_app")
    assert steam.steam_window(w)
    assert windows.title_has("Visual Studio Code")(windows.Win(2, "app.py - capricorn - Visual Studio Code", "code.exe"))
    assert windows.explorer_folder("Downloads")(windows.Win(3, "Downloads", "explorer.exe", "CabinetWClass"))
    assert windows.browser_window(windows.Win(4, "YouTube Music - Opera", "opera.exe"))
