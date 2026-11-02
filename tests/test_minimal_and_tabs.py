import os, tempfile
os.environ.setdefault("CAPRICORN_HOME", tempfile.mkdtemp())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from capricorn.actions.browser_tab import find_tab_window
from capricorn.brain import rules

WINDOWS = [
    (1, "Inbox (3) - Gmail - Opera"),
    (2, "Shelter - Porter Robinson - YouTube Music - Opera"),
    (3, "Lofi Girl - YouTube - Google Chrome"),
    (4, "YouTube Music"),                                   # desktop app, not a browser tab
    (5, "capricorn-assistant - Visual Studio Code"),
]

def test_reuses_youtube_music_tab():
    assert find_tab_window("https://music.youtube.com/watch?v=x", WINDOWS)[0] == 2

def test_reuses_youtube_tab_not_music():
    assert find_tab_window("https://www.youtube.com/watch?v=x", WINDOWS)[0] == 3

def test_no_matching_tab():
    assert find_tab_window("https://music.youtube.com/watch?v=x", WINDOWS[:1] + WINDOWS[3:]) is None
    assert find_tab_window("https://github.com", WINDOWS) is None

@pytest.mark.parametrize("text,op", [
    ("minimal mode", "minimal_on"), ("enable minimal mode", "minimal_on"), ("go minimal", "minimal_on"),
    ("switch to minimal mode", "minimal_on"), ("disable minimal mode", "minimal_off"),
    ("minimal mode off", "minimal_off"), ("normal mode", "minimal_off"), ("switch back to normal mode", "minimal_off"),
    ("hide yourself", "hide"), ("stay hidden", "hide"), ("show yourself", "show"), ("stay on screen", "show"),
])
def test_ui_commands(text, op):
    assert rules.parse(text) == ("_ui", {"op": op})

def test_plain_hide_is_temporary():
    assert rules.parse("hide") == ("_goodbye", {})


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])

def test_sprite_modes_and_dance(qapp):
    from capricorn.ui.sprite import Sprite
    sp = Sprite(0.42, 0.36, "normal")
    for a in ["dance", "glitch", "min_idle", "min_glitch", "min_talking", "talking", "blink"]:
        assert sp.has(a), a
    assert sp.width() == sp.height()
    sp.set_music(True)
    assert sp._anim_name == "dance"
    sp.talk_for(600, then="smile")
    assert sp._anim_name == "talking" and sp.busy
    sp._end_talk()
    assert sp._anim_name == "dance"          # music still playing -> back to dancing
    sp.set_music(False)
    assert sp._anim_name is None and sp.current == "neutral"
    sp.set_mode("minimal")
    assert sp.mode == "minimal" and sp.width() > sp.height() and sp._anim_name == "min_idle"
    sp.set_pose("angry")                      # minimal has no poses -> stays on idle loop
    assert sp._anim_name == "min_idle"
    sp.talk_for(600, then="smile")
    assert sp._anim_name == "min_talking"
    sp._end_talk()
    assert sp._anim_name == "min_idle"
    sp.glitch()
    assert sp._anim_name == "min_glitch"

def test_overlay_minimal_has_no_bubble(qapp):
    from capricorn.config import Settings, ensure_user_files
    from capricorn.ui.overlay import Overlay
    ensure_user_files()
    ov = Overlay(Settings())
    ov.set_mode("minimal")
    assert ov.minimal and ov.always_visible()
    ov.show_reply("Opening YouTube.", "smile")
    assert not ov.bubble.isVisible() and ov.sprite._anim_name == "min_talking"
    ov.show_reply("Shut down the PC?", "surprised", ask=True)   # questions still need the bubble
    assert ov.bubble.isVisible()
    ov.set_mode("normal")
    assert not ov.minimal
