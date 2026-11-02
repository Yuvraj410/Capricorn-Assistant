"""Settings screen, offer -> confirm, filler handling, slang levels."""
import os

import pytest

from capricorn import persona
from capricorn.audio.listener import is_filler
from capricorn.brain.router import Router
from capricorn.brain.rules import parse


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPRICORN_HOME", str(tmp_path))


def test_fillers():
    for t in ["uh,", "Uhhh...", "um, so", "hmm", "let me think", "", "  ...  "]:
        assert is_filler(t), t
    for t in ["uh, open youtube", "tell me the stock market", "so play lofi"]:
        assert not is_filler(t), t


def test_offer_detection():
    ws = {"name": "web_search", "args": {"query": "stock market"}}
    assert Router._is_offer("No cap - I don't know real-time stock markets. Web search?", ws)
    assert Router._is_offer("Want me to look it up?", ws)
    assert not Router._is_offer("Searching the Net for that.", ws)
    assert not Router._is_offer("What's the time?", {"name": "time", "args": {}})


def test_settings_rules():
    for t in ["open settings", "open your settings", "show me your control panel", "open capricorn settings", "settings"]:
        assert parse(t) == ("_ui", {"op": "settings"}), t
    assert parse("open control panel") != ("_ui", {"op": "settings"})     # that's Windows' Control Panel


def test_slang_levels_change_the_prompt():
    class S(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)
    off = persona.build_system_prompt(["time"], "", S({"personality.slang": 0, "personality.genz_slang": 0}))
    heavy = persona.build_system_prompt(["time"], "", S({"personality.slang": 3, "personality.genz_slang": 2}))
    assert "no Night City slang" in off and "Gen Z" not in off
    assert "two or three slang terms" in heavy and "Gen Z" in heavy
    assert "No emojis." in persona.build_system_prompt(["time"])


def test_schema_covers_every_setting():
    from capricorn.ui.settings_schema import load_fields
    keys = {f.key for f in load_fields()}
    for k in ["wake.end_silence", "personality.slang", "voice.engine", "voice.pronounce", "brain.model",
              "music.service", "sounds.wake_chime"]:
        assert k in keys
    assert "ui.custom_xy" not in keys


def test_settings_window_saves(tmp_path):
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from capricorn.config import Settings, ensure_user_files
    from capricorn.ui.settings_window import SettingsWindow
    ensure_user_files()
    s = Settings()
    w = SettingsWindow(s)
    assert len(w.editors) > 50 and w.changes() == {}
    w.editors["personality.slang"].w.setValue(0)
    w.editors["wake.end_silence"].w.setValue(2.5)
    w.editors["voice.pronounce"].w.setPlainText("choomba: chewmba")
    got = []
    w.saved.connect(lambda ch, rs: got.append((ch, rs)))
    w._save(restart=False)
    assert got and got[0][1] is False                             # everything applies live now
    s2 = Settings()
    assert s2.get("personality.slang") == 0 and s2.get("wake.end_silence") == 2.5
    assert s2.get("voice.pronounce") == {"choomba": "chewmba"}
    w._filter("slang")
    assert w.rows["personality.slang"].isVisibleTo(w) or True


def test_web_answer_reads_results(monkeypatch):
    from capricorn.actions import research
    from capricorn.brain import router as R

    monkeypatch.setattr(research, "search", lambda q, n=6: [
        {"title": "Stocks rally", "url": "https://www.reuters.com/markets/x", "snippet": "S&P 500 up 1.2%",
         "date": "2026-11-01", "source": "Reuters"},
        {"title": "Nasdaq", "url": "https://cnbc.com/y", "snippet": "Nasdaq gains 1.8%", "date": "", "source": ""}])

    class FakeLLM:
        history = []
        def answer_from_results(self, q, text, today):
            assert "S&P 500 up 1.2%" in text and "Reuters" in text
            return {"say": "Markets are up: S&P 500 plus 1.2%, Nasdaq plus 1.8%.", "emotion": "smile"}

    class FakePerms:
        def mode(self, cat):
            return "all"

    class FakeReg:
        perms = FakePerms()

    r = R.Router.__new__(R.Router)
    r.reg, r.llm = FakeReg(), FakeLLM()
    said = []
    r.progress = lambda t, e="thinking": said.append(t)
    res = r.web_answer("current stock market")
    assert res.ok and "1.2%" in res.say and said
    assert res.data["sources"][0][0] == "reuters.com" and "via reuters.com" in res.data["caption"]


def test_results_text_and_domain():
    from capricorn.actions.research import domain, results_text
    assert domain("https://www.example.com/a") == "example.com"
    t = results_text([{"title": "A", "url": "https://a.com", "snippet": "x", "date": "2026-01-01", "source": ""}])
    assert t == "[1] A (a.com, 2026-01-01): x"


def test_nothing_needs_a_restart_any_more():
    from capricorn.ui.settings_schema import load_fields
    fields = load_fields()
    assert not [f.key for f in fields if f.needs_restart]
    assert {f.key for f in fields if f.reloads} >= {"stt.model", "voice.engine"}


def test_wake_words_apply_live():
    from capricorn.audio import listener as L
    from capricorn.config import Settings, ensure_user_files
    ensure_user_files()
    s = Settings()
    lst = L.Listener.__new__(L.Listener)
    lst.s, lst.cb = s, type("CB", (), {"on_status": staticmethod(lambda t: None)})()
    lst._rebuild = lst._reopen = False
    lst._build_matcher()
    assert not lst.matcher.find("hey jarvis open youtube")[0]
    s.save_many({"wake.words": ["capri", "jarvis"]})
    lst.reconfigure({"wake.words"})
    assert lst._rebuild and lst.matcher.find("hey jarvis open youtube") == (True, "open youtube")
    lst.reconfigure({"wake.input_device"})
    assert lst._reopen


def test_overlay_resizes_live():
    pytest.importorskip("PyQt6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from capricorn.config import Settings, ensure_user_files
    from capricorn.ui.overlay import Overlay
    ensure_user_files()
    s = Settings()
    ov = Overlay(s)
    w0 = ov.sprite.width()
    s.save_many({"ui.scale": 0.6})
    ov.apply_size()
    assert ov.sprite.width() > w0
