"""Closing games/apps. Uses a real process started from a fake game folder."""
import os, shutil, subprocess, sys, tempfile, time
os.environ.setdefault("CAPRICORN_HOME", tempfile.mkdtemp())

import pytest
from capricorn.actions import close, steam
from capricorn.actions.apps import AppEntry, AppIndex
from capricorn.brain import rules
from capricorn.config import ensure_user_files
from capricorn.security.permissions import Permissions


@pytest.mark.parametrize("text,intent", [
    ("close the game", "close_game"), ("quit game", "close_game"), ("kill the game", "close_game"),
    ("close black myth wukong", "close_app"), ("quit discord", "close_app"), ("exit steam", "close_app"),
    ("stop elden ring", "_stop"), ("close this tab", "close_tab"), ("close the youtube tab", "close_tab"),
    ("stop the music", "media"), ("shut down the computer", "system"), ("stop listening", "_goodbye"),
])
def test_close_rules(text, intent):
    assert rules.parse(text)[0] == intent


@pytest.fixture
def fake_game(tmp_path, monkeypatch):
    folder = tmp_path / "steamapps" / "common" / "FakeGame"
    folder.mkdir(parents=True)
    exe = folder / ("FakeGame" + os.path.splitext(sys.executable)[1])
    shutil.copy2(os.path.realpath(sys.executable), exe)
    env = dict(os.environ, PYTHONHOME=sys.base_prefix)   # copied python still finds its stdlib
    proc = subprocess.Popen([str(exe), "-c", "import time; time.sleep(60)"], env=env)
    time.sleep(0.5)
    idx = AppIndex()
    idx.entries = [AppEntry("Fake Game", "999", "steam", str(folder))]
    idx._last = 9e18
    monkeypatch.setattr(steam, "_open", lambda url: None)
    monkeypatch.setattr(steam, "_show_steam", lambda delay=0.0: None)
    yield idx, proc
    if proc.poll() is None:
        proc.kill()


def test_finds_running_game(fake_game):
    idx, proc = fake_game
    running = close.running_steam_games(idx)
    assert running and running[0][0].name == "Fake Game"
    assert proc.pid in {p.pid for p in running[0][1]}


def test_close_game_asks_before_force_then_stops_it(fake_game):
    ensure_user_files("full")
    idx, proc = fake_game
    r = close.close_game("fake game", idx, Permissions(), grace=1.0, ask=True)
    assert r.confirm_question and "Force-stop" in r.confirm_question      # didn't close by itself
    assert proc.poll() is None                                              # nothing killed yet
    out = r.confirm_run()
    proc.wait(timeout=5)
    assert proc.poll() is not None and out.ok


def test_close_game_when_nothing_running(tmp_path):
    ensure_user_files("full")
    idx = AppIndex(); idx.entries = [AppEntry("Fake Game", "999", "steam", str(tmp_path))]; idx._last = 9e18
    assert "isn't running" in close.close_game("fake game", idx, Permissions()).say
    assert "No Steam game" in close.close_game("", idx, Permissions()).say


def test_close_game_default_stops_like_steam_without_asking(fake_game):
    ensure_user_files("full")
    idx, proc = fake_game
    r = close.close_game("fake game", idx, Permissions(), grace=1.0)
    assert r.confirm_question is None
    proc.wait(timeout=5)
    assert proc.poll() is not None


def test_pick_tab_window():
    from capricorn.actions.browser_tab import pick_tab_window
    wins = [(1, "Capri", "pythonw.exe", False), (2, "Inbox - Gmail - Opera", "opera.exe", True),
            (3, "Lofi Girl - YouTube - Opera", "opera.exe", False)]
    assert pick_tab_window("", wins)[0] == 2          # the browser you're in
    assert pick_tab_window("youtube", wins)[0] == 3
    assert pick_tab_window("reddit", wins) is None
    assert pick_tab_window("", [(1, "Capri", "pythonw.exe", True)]) is None


def test_folder_phrasings():
    for t, name in [("open the folder of Capricorn Assistant", "capricorn assistant"),
                    ("open the folder Capricorn", "capricorn"), ("now open the Capricorn folder", "the capricorn folder")]:
        assert rules.parse(t) == ("open_folder", {"name": name})
    from capricorn.actions.files import _clean
    assert _clean("the capricorn folder") == "capricorn" and _clean("folder of capricorn assistant") == "capricorn assistant"


def test_never_launches_itself():
    from capricorn.actions.apps import NEVER_LAUNCH
    assert NEVER_LAUNCH.search("Capricorn") and NEVER_LAUNCH.search("Capricorn") and not NEVER_LAUNCH.search("Capri Sun Tracker")
