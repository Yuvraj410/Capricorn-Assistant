import os, tempfile
from pathlib import Path
import pytest

os.environ["CAPRICORN_HOME"] = tempfile.mkdtemp()

from capricorn.brain import rules
from capricorn.security.permissions import Permissions, ALLOW, ASK, DENY
from capricorn import paths


@pytest.mark.parametrize("text,intent,args", [
    ("Open YouTube.", "_open", {"name": "youtube"}),
    ("please open steam", "_open", {"name": "steam"}),
    ("open my downloads folder", "open_folder", {"name": "my downloads folder"}),
    ("open github.com", "open_url", {"url": "github.com"}),
    ("open the resume pdf", "open_file", {"name": "the resume pdf"}),
    ("play lofi beats", "music_play", {"query": "lofi beats"}),
    ("play some music", "music_play", {"query": ""}),
    ("play never gonna give you up on youtube", "youtube_play", {"query": "never gonna give you up"}),
    ("play skyrim on steam", "open_app", {"name": "skyrim", "steam": True}),
    ("launch the game hollow knight", "open_app", {"name": "hollow knight", "steam": True}),
    ("play the cyberpunk game", "open_app", {"name": "the cyberpunk", "steam": True}),
    ("play porter robinson on youtube music", "music_play", {"query": "porter robinson"}),
    ("pause", "media", {"command": "pause"}),
    ("pause the music", "media", {"command": "pause"}),
    ("pause this song", "media", {"command": "pause"}),
    ("pause this song which is playing right now", "media", {"command": "pause"}),
    ("can you stop the music for a sec", "media", {"command": "pause"}),
    ("stop", "media", {"command": "pause"}),
    ("resume", "media", {"command": "play"}),
    ("play the music again", "media", {"command": "play"}),
    ("unpause it", "media", {"command": "play"}),
    ("next song", "media", {"command": "next"}),
    ("skip", "media", {"command": "next"}),
    ("go back a track", "media", {"command": "previous"}),
    ("turn it up", "media", {"command": "volume_up"}),
    ("volume down please", "media", {"command": "volume_down"}),
    ("what's playing", "now_playing", {}),
    ("what time is it", "time", {}),
    ("lock the pc", "system", {"op": "lock"}),
    ("shut down the computer", "system", {"op": "shutdown"}),
    ("search for rtx 5070 benchmarks", "web_answer", {"query": "rtx 5070 benchmarks"}),
    ("search youtube for cyberpunk edgerunners trailer", "youtube_search", {"query": "cyberpunk edgerunners trailer"}),
    ("thanks", "_thanks", {}),
    ("never mind", "_goodbye", {}),
    ("hello", "_greeting", {}),
])
def test_rules(text, intent, args):
    assert rules.parse(text) == (intent, args)


@pytest.mark.parametrize("text", ["tell me a joke", "how are you doing today", "what's the capital of france"])
def test_rules_fall_through_to_llm(text):
    assert rules.parse(text) is None


def _perms(profile):
    return Permissions(paths.DEFAULTS_DIR / f"permissions.{profile}.yaml")


def test_safe_profile():
    p = _perms("safe")
    assert p.check_app("Steam").verdict == ASK
    assert p.check_url("https://youtube.com").verdict == ALLOW
    assert p.check_url("file:///C:/x").verdict == DENY
    assert p.check_folder(Path.home() / "Downloads").verdict == ALLOW
    assert p.check_folder("/etc").verdict == DENY
    assert p.check_file(Path.home() / "Downloads" / "evil.exe").verdict == DENY
    assert p.check_system("lock").verdict == ALLOW
    assert p.check_system("shutdown").verdict == ASK


def test_full_profile():
    p = _perms("full")
    assert p.check_app("Steam").verdict == ALLOW
    assert p.check_folder("/etc").verdict == ALLOW
    assert p.check_file(Path.home() / "x.ps1").verdict == DENY      # never opened as a file
    assert p.check_system("shutdown").verdict == ASK               # power always confirms
    assert p.check_system("lock").verdict == ALLOW


def test_llm_parse_validates_actions():
    from capricorn.brain.llm import LLM
    out = LLM._parse('{"say":"Opening it","emotion":"smile","action":{"name":"rm_rf","args":{}}}', ["open_url"])
    assert out["action"] is None
    out = LLM._parse('<think>x</think>{"say":"hi","emotion":"weird","action":{"name":"open_url","args":{"url":"https://a.com"}}}', ["open_url"])
    assert out["emotion"] == "neutral" and out["action"]["name"] == "open_url"
    assert LLM._parse("plain text reply", [])["say"] == "plain text reply"


def test_voice_volume_rules():
    from capricorn.brain.rules import parse
    for t in ["speak louder", "talk a bit louder", "I can't hear you", "turn yourself up"]:
        assert parse(t) == ("_ui", {"op": "voice_louder"}), t
    for t in ["speak quieter", "you're too loud", "turn your voice down"]:
        assert parse(t) == ("_ui", {"op": "voice_quieter"}), t
    assert parse("volume up") == ("media", {"command": "volume_up"})
    assert parse("louder") == ("media", {"command": "volume_up"})
