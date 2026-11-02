"""Audio ducking logic with a fake Windows mixer."""
import json
import os

import pytest

from capricorn import paths
from capricorn.audio.ducking import Ducker, STATE_FILE


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPRICORN_HOME", str(tmp_path))


class Vol:
    def __init__(self, v):
        self.v = v

    def GetMasterVolume(self):
        return self.v

    def SetMasterVolume(self, v, ctx):
        self.v = v


class Proc:
    def __init__(self, n):
        self.n = n

    def name(self):
        return self.n


class Sess:
    def __init__(self, pid, name, v):
        self.ProcessId, self.Process, self.SimpleAudioVolume = pid, Proc(name), Vol(v)


def make(sessions):
    d = Ducker(level=0.25, fade_ms=30, enabled=False)
    d._au = type("AU", (), {"GetAllSessions": staticmethod(lambda: sessions)})
    return d


def test_duck_lowers_others_and_restores():
    music, game = Sess(100, "opera.exe", 0.8), Sess(200, "game.exe", 1.0)
    me, system = Sess(os.getpid(), "python.exe", 1.0), Sess(0, "", 1.0)
    d = make([music, game, me, system])
    d._do_duck()
    assert music.SimpleAudioVolume.v == pytest.approx(0.2) and game.SimpleAudioVolume.v == pytest.approx(0.25)
    assert me.SimpleAudioVolume.v == 1.0 and system.SimpleAudioVolume.v == 1.0     # Capri + system untouched
    assert (paths.user_dir() / STATE_FILE).exists()                                  # crash safety
    d._do_duck()                                                                     # twice: no double-duck
    assert music.SimpleAudioVolume.v == pytest.approx(0.2)
    d._do_restore()
    assert music.SimpleAudioVolume.v == pytest.approx(0.8) and game.SimpleAudioVolume.v == pytest.approx(1.0)
    assert not (paths.user_dir() / STATE_FILE).exists()


def test_restore_respects_manual_changes():
    music = Sess(100, "opera.exe", 0.8)
    d = make([music])
    d._do_duck()
    music.SimpleAudioVolume.v = 0.5            # user moved the slider while ducked
    d._do_restore()
    assert music.SimpleAudioVolume.v == 0.5


def test_recovers_after_crash():
    music = Sess(100, "opera.exe", 0.2)
    (paths.user_dir() / STATE_FILE).write_text(json.dumps({"opera.exe:100": [0.8, 0.2]}))
    d = make([music])
    d._recover()
    assert music.SimpleAudioVolume.v == pytest.approx(0.8)
    assert not (paths.user_dir() / STATE_FILE).exists()
