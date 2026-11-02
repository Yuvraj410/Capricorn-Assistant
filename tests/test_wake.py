import pytest
import yaml
from capricorn import paths
from capricorn.audio.wake import WakeMatcher

cfg = yaml.safe_load(open(paths.DEFAULTS_DIR / "settings.yaml"))["wake"]
M = WakeMatcher(cfg["words"], cfg["aliases"])

@pytest.mark.parametrize("heard,cmd", [
    ("Hey Capri, open YouTube.", "open YouTube."),
    ("Capricorn open steam", "open steam"),
    ("Hey Capricorn, play lofi beats", "play lofi beats"),
    ("Capri con, what time is it?", "what time is it?"),
    ("Okay Kapri. Next song.", "Next song."),
    ("Hey, Capree.", ""),
    ("Capri", ""),
    ("hey capricone pause", "pause"),
])
def test_wake_found(heard, cmd):
    found, rest = M.find(heard)
    assert found, heard
    assert rest == cmd

@pytest.mark.parametrize("heard", [
    "I was talking to my friend about cars", "open youtube", "hey can you pass the salt",
    "copy that", "the weather is nice today",
])
def test_no_wake(heard):
    assert not M.find(heard)[0], heard

@pytest.mark.parametrize("heard,cmd", [
    ("Capri open YouTube", "open YouTube"), ("Capri pause", "pause"), ("Capri play music", "play music"),
    ("Capri, call mom", "call mom"), ("Capri con open steam", "open steam"), ("Capri code", "code"),
    ("Hey Capri copy this", "copy this"), ("Capri cancel", "cancel"),
])
def test_does_not_eat_command(heard, cmd):
    assert M.find(heard) == (True, cmd)


MS = WakeMatcher(cfg["words"], cfg["aliases"], short_forms=cfg["short_words"])

@pytest.mark.parametrize("heard,cmd", [
    ("Hey C, open YouTube.", "open YouTube."), ("Hey see", ""), ("Hey, C.", ""), ("OK C, pause", "pause"),
    ("C, open steam", "open steam"), ("See, play my liked music", "play my liked music"),
    ("Sea, what time is it?", "what time is it?"), ("C next song", "next song"),
    ("Hey Capri, open YouTube", "open YouTube"),            # long wake words still work
])
def test_short_wake(heard, cmd):
    assert MS.find(heard) == (True, cmd)

@pytest.mark.parametrize("heard", [
    "I see what you mean", "See you later", "See ya", "C is a great language", "C plus plus is hard",
    "the sea is calm", "Let me see", "see the thing over there", "I got a C on the test", "C",
])
def test_short_wake_ignores_normal_speech(heard):
    assert not MS.find(heard)[0], heard

def test_vosk_vocab_has_short_words():
    assert {"see", "c"} <= set(MS.vosk_vocab())


def test_whisper_variants_of_hey_c():
    from capricorn.audio.wake import WakeMatcher
    m = WakeMatcher(["capri", "capricorn"], [], short_forms=["c", "see", "sea", "si", "cee", "ce"])
    assert m.find("Hey, Siri, open YouTube.") == (True, "open YouTube.")
    assert m.find("Hey, C.") == (True, "")
    assert m.find("AC, play my liked music") == (True, "play my liked music")
    assert m.find("HC") == (True, "")
    assert m.find("Siri, open YouTube")[0] is False      # needs the "hey"
    assert m.find("Hey, see you later")[0] is False


def test_stt_hallucination_filter():
    from capricorn.audio.stt import is_hallucination, _loud_enough
    import numpy as np
    assert is_hallucination("Thanks for watching!")
    assert not is_hallucination("thank you")
    assert not _loud_enough(np.zeros(16000, np.float32))
    assert _loud_enough(np.full(16000, 0.05, np.float32))
