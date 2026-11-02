"""Listener control flow with a fake Vosk recogniser, fake microphone and fake Whisper."""
import json, os, sys, tempfile, time, types
import numpy as np
os.environ.setdefault("CAPRICORN_HOME", tempfile.mkdtemp())

from capricorn.config import Settings
from capricorn.audio import listener as L

LOUD = (np.sin(np.linspace(0, 400, L.BLOCK)) * 8000).astype(np.int16)
QUIET = np.zeros(L.BLOCK, np.int16)


class FakeRec:
    """Final result after a loud->quiet transition; text decided by the test."""
    script = []
    def __init__(self, *a): self.loud = 0
    def SetWords(self, v): pass
    def Reset(self): self.loud = 0
    def AcceptWaveform(self, data):
        a = np.frombuffer(data, np.int16)
        if np.abs(a).max() > 1000:
            self.loud += 1
            return False
        if self.loud:
            self.loud = 0
            return True
        return False
    def Result(self):
        word = FakeRec.script.pop(0) if FakeRec.script else ""
        res = [{"word": word, "conf": 0.9}] if word else []
        return json.dumps({"text": word, "result": res})
    def PartialResult(self): return json.dumps({"partial": ""})


def make(stt_texts):
    vosk = types.ModuleType("vosk")
    vosk.Model = lambda p: object(); vosk.SetLogLevel = lambda n: None; vosk.KaldiRecognizer = FakeRec
    sys.modules["vosk"] = vosk
    L.find_vosk_model = lambda: "/fake"
    s = Settings()
    s.data["wake"]["command_timeout"] = 1.5
    s.data["wake"]["end_silence"] = 0.3
    stt = types.SimpleNamespace(transcribe=lambda audio, hotwords=None: stt_texts.pop(0) if stt_texts else "")
    events = []
    cb = L.Callbacks(on_wake=lambda: events.append("wake"), on_wake_cancel=lambda: events.append("cancel"),
                     on_listening=lambda: events.append("listening"),
                     on_command=lambda c, h: events.append(("command", c)),
                     on_no_command=lambda: events.append("no_command"),
                     on_capture=lambda k, t: events.append(("capture", k, t)),
                     on_error=lambda m: events.append(("error", m)))
    lst = L.Listener(s, stt, cb)
    lst._open_stream = lambda: True
    return lst, events


def feed(lst, blocks):
    for b in blocks:
        lst.q.put(b)
        time.sleep(0.002)


def run_until(events, pred, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred(events):
            return True
        time.sleep(0.02)
    return False


def test_wake_plus_command_in_one_sentence():
    FakeRec.script = ["capri"]
    lst, ev = make(["Hey Capri, open YouTube."])
    lst.start()
    feed(lst, [QUIET] * 3 + [LOUD] * 10 + [QUIET] * 3)
    assert run_until(ev, lambda e: ("command", "open YouTube.") in e), ev
    assert ev[0] == "wake"
    lst.stop()


def test_bare_wake_then_command():
    FakeRec.script = ["capri"]
    lst, ev = make(["Hey Capri.", "what's playing"])
    lst.start()
    feed(lst, [QUIET] * 3 + [LOUD] * 6 + [QUIET] * 3)
    assert run_until(ev, lambda e: "listening" in e), ev
    feed(lst, [QUIET] * 2 + [LOUD] * 8 + [QUIET] * 6)
    assert run_until(ev, lambda e: ("command", "what's playing") in e), ev
    lst.stop()


def test_false_alarm_is_cancelled():
    FakeRec.script = ["capri"]
    lst, ev = make(["I was talking about a car"])
    lst.start()
    feed(lst, [QUIET] * 3 + [LOUD] * 6 + [QUIET] * 3)
    assert run_until(ev, lambda e: "cancel" in e), ev
    assert not any(isinstance(x, tuple) and x[0] == "command" for x in ev)
    lst.stop()


def test_bare_wake_then_silence_times_out():
    FakeRec.script = ["capri"]
    lst, ev = make(["Capri"])
    lst.start()
    feed(lst, [QUIET] * 3 + [LOUD] * 6 + [QUIET] * 3)
    feed(lst, [QUIET] * 25)
    assert run_until(ev, lambda e: "no_command" in e, timeout=6), ev
    lst.stop()


def test_confirm_capture():
    FakeRec.script = []
    lst, ev = make(["yes do it"])
    lst.start()
    time.sleep(0.2)
    lst.request_capture("confirm", timeout=2)
    time.sleep(0.3)
    feed(lst, [QUIET] * 2 + [LOUD] * 5 + [QUIET] * 6)
    assert run_until(ev, lambda e: ("capture", "confirm", "yes do it") in e), ev
    lst.stop()


def test_pause_mid_command_is_not_cut_off():
    """'Hey Capri, play my ... liked music' - the pause after 'my' must not end the command."""
    FakeRec.script = ["capri"]
    stt_calls = []
    def stt(audio, hotwords=None):
        stt_calls.append(len(audio))
        return "Hey Capri, play my liked music" if len(audio) > 1.5 * L.RATE else "Hey Capri, play my"
    lst, ev = make([])
    lst.stt.transcribe = stt
    lst.s.data["wake"]["end_silence"] = 1.0
    lst.start()
    feed(lst, [QUIET] * 3 + [LOUD] * 8 + [QUIET] * 5 + [LOUD] * 8 + [QUIET] * 14)
    assert run_until(ev, lambda e: any(isinstance(x, tuple) and x[0] == "command" for x in e), timeout=6), ev
    assert ("command", "play my liked music") in ev, ev
    lst.stop()


def test_vosk_short_wake_word_gating():
    lst, _ev = make([])
    def res(*words):
        return {"result": [{"word": w, "conf": 0.9} for w in words]}
    assert lst._vosk_wake(res("see", "[unk]", "[unk]"))          # "C, open youtube"
    assert lst._vosk_wake(res("hey", "see"))                      # "hey C"
    assert not lst._vosk_wake(res("[unk]", "see", "[unk]"))       # "I see that"
    assert lst._vosk_wake(res("[unk]", "capri", "[unk]"))         # long wake words: anywhere
    assert not lst._has_wake_token("see")                         # no early pop-up for "see"
    assert lst._has_wake_token("capri")


def test_vosk_maybe_short_is_checked_quietly():
    lst, ev = make([])
    def res(*words):
        return {"result": [{"word": w, "conf": 0.9} for w in words]}
    assert lst._vosk_maybe_short(res("[unk]", "see", "[unk]"))
    assert not lst._vosk_maybe_short(res("[unk]", "[unk]", "see"))
    lst.stt.transcribe = lambda a, hotwords=None: "I see that"
    lst._handle_wake(L.np.zeros(16000, L.np.int16), quiet=True)
    assert ev == [], ev                                     # rejected silently - no pop-up


def test_vad_end_of_speech_on_silence():
    lst, _ev = make([])
    blocks = [L.np.zeros(L.BLOCK, L.np.int16) for _ in range(25)]
    assert lst._speech_ended(blocks, 1.2) is True
    assert lst._speech_ended(blocks[:5], 1.2) is False          # too little audio to judge yet
