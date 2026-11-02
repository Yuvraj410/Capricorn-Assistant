"""Capri's voice: text prep, the worker protocol, and the client (with a fake worker - no torch needed)."""
import io
import json
import sys
import textwrap
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from capricorn import paths
from capricorn.tts import textprep
from capricorn.tts import worker as W


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPRICORN_HOME", str(tmp_path / "data"))
    return tmp_path


# -- text prep ---------------------------------------------------------------------------------------
def test_clean_strips_markup_emoji_urls():
    t = textprep.clean("*smirks* Done, choom 😎 — see https://youtu.be/x & **enjoy**")
    assert t == "Done, choom, see that link and enjoy"


def test_sentences_glue_tiny_fragments():
    assert textprep.sentences("Preem. Lo-fi's queued, choom. Try not to fall asleep.") == \
        ["Preem. Lo-fi's queued, choom.", "Try not to fall asleep."]
    assert textprep.sentences("On it.") == ["On it."]
    assert len(textprep.sentences(" ".join(f"Sentence number {i} here." for i in range(12)))) == 6


def test_emotion_tags():
    assert textprep.for_speech("Ha, you wish.", "laughing")[0].startswith("[chuckle] ")
    assert not textprep.for_speech("Ha, you wish.", "laughing", tags=False)[0].startswith("[")
    assert textprep.for_speech("Fine.", "smile") == ["Fine."]
    assert textprep.for_speech("😎", "smile") == []


# -- worker ------------------------------------------------------------------------------------------
class FakeVoice:
    def __init__(self):
        self.said = []

    def say(self, text, out, style="", seed=None, temperature=None, loudness=None):
        time.sleep(0.05)
        self.said.append(text)
        return W.write_wav(Path(out), np.zeros(2400, np.float32), 24000)


def test_worker_serve_skips_superseded_requests(tmp_path):
    reqs = [{"id": 1, "gen": 1, "text": "old one", "out": str(tmp_path / "1.wav")},
            {"id": 2, "gen": 1, "text": "old two", "out": str(tmp_path / "2.wav")},
            {"id": 3, "gen": 2, "text": "new", "out": str(tmp_path / "3.wav")}]
    inp = io.StringIO("".join(json.dumps(r) + "\n" for r in reqs))
    out = io.StringIO()
    v = FakeVoice()
    W.serve(v, inp, out)
    msgs = [json.loads(x) for x in out.getvalue().splitlines()]
    by = {m["id"]: m for m in msgs}
    assert by[3]["ok"] and by[3]["ms"] == 100
    assert "new" in v.said
    assert any(by[i].get("skipped") for i in (1, 2))        # older reply interrupted
    assert (tmp_path / "3.wav").exists()


def test_write_wav_clips_and_reports_ms(tmp_path):
    ms = W.write_wav(tmp_path / "a.wav", np.full(48000, 3.0, np.float32), 24000)
    assert ms == 2000
    from capricorn.tts.capri_voice import read_wav
    data, sr = read_wav(tmp_path / "a.wav")
    assert sr == 24000 and data.max() <= 32767 and data.max() > 30000


def test_conds_cache_name_changes_with_reference(tmp_path):
    ref = tmp_path / "capri.wav"
    ref.write_bytes(b"x" * 10)
    a = W.conds_path(ref)
    ref.write_bytes(b"x" * 20)
    assert W.conds_path(ref) != a and a.name.startswith("capri.chatterbox-turbo.")


# -- client with a fake worker process --------------------------------------------------------------
FAKE_WORKER = textwrap.dedent('''
    import json, sys, wave
    print(json.dumps({"ready": True, "device": "cpu", "gpu": "", "sr": 24000, "load_s": 0.1}), flush=True)
    for line in sys.stdin:
        r = json.loads(line)
        if r.get("cmd") == "quit":
            break
        with wave.open(r["out"], "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b"\\0\\0" * 2400)
        print(json.dumps({"id": r["id"], "ok": True, "file": r["out"], "ms": 100, "took": 0.01}), flush=True)
''')


class FakePlayer:
    def __init__(self):
        self.played = []
        self.stopped = 0

    def play(self, path):
        self.played.append(Path(path).name)
        time.sleep(0.02)
        return True

    def stop(self):
        self.stopped += 1


def make_client(tmp_path):
    from capricorn.tts.capri_voice import CapriVoice
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER)
    ref = tmp_path / "capri.wav"
    W.write_wav(ref, np.zeros(24000 * 6, np.float32), 24000)
    status = []
    c = CapriVoice(ref, cmd=[sys.executable, str(script)], player=FakePlayer(), on_status=status.append)
    c.start()
    assert c.ready.wait(10), status
    return c, status


def test_client_speaks_sentence_by_sentence_and_caches(tmp_path):
    c, status = make_client(tmp_path)
    try:
        assert "online" in status[-1]
        chunks, done = [], threading.Event()
        res = {}
        parts = ["Lo-fi's queued, choom.", "Try not to fall asleep."]
        assert c.speak(parts, chunks.append, lambda ok: (res.setdefault("ok", ok), done.set()))
        assert done.wait(10)
        assert res["ok"] and chunks == [100, 100] and len(c.player.played) == 2
        assert all(c.cache_file(p).exists() for p in parts)
        # second time: straight from the cache, even if the worker is gone
        c.close()
        c.ready.clear()
        done.clear()
        assert c.speak(parts, chunks.append, lambda ok: done.set())
        assert done.wait(5) and len(c.player.played) == 4
        assert not c.speak(["Never said before."], chunks.append, lambda ok: None)
    finally:
        c.close()


def test_client_reports_missing_reference(tmp_path):
    from capricorn.tts.capri_voice import CapriVoice
    status = []
    c = CapriVoice(tmp_path / "nope.wav", cmd=[sys.executable, "-c", "pass"], player=FakePlayer(),
                   on_status=status.append)
    c._spawn()
    assert "reference missing" in c.failed and not c.ready.is_set()


def test_engine_auto_falls_back_to_text(tmp_path):
    from capricorn.config import Settings
    from capricorn.tts.engine import TTS
    s = Settings()
    t = TTS(s)
    assert t.engine() == "none"                        # no voice env in a fresh data folder
    assert t.speak("Hello there, choom.") is False


def test_listener_ignores_mic_while_speaking():
    from capricorn.audio import listener as L
    lst = L.Listener.__new__(L.Listener)
    lst.muted, lst.speaking, lst._speak_tok = False, False, 0
    import queue
    lst.q = queue.Queue()
    lst.hold_speaking()
    lst._audio_cb(np.ones((10, 1), np.int16), 10, None, None)
    assert lst.q.empty()
    lst.release_speaking(0)
    lst._audio_cb(np.ones((10, 1), np.int16), 10, None, None)
    assert not lst.q.empty()


def test_normalize_makes_quiet_speech_louder_without_clipping():
    sr = 24000
    t = np.arange(sr * 2) / sr
    quiet = (0.03 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    out = W.normalize(quiet, sr, -16.0)
    assert np.max(np.abs(out)) > 0.3 and np.max(np.abs(out)) < 0.99
    loud = (1.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    assert np.max(np.abs(W.normalize(loud, sr, -10.0))) < 0.99


def test_player_volume_scales_and_clips(tmp_path, monkeypatch):
    from capricorn.tts import capri_voice as CV
    W.write_wav(tmp_path / "a.wav", np.full(2400, 0.5, np.float32), 24000)
    got = {}
    import types
    fake_sd = types.SimpleNamespace(play=lambda d, sr: got.setdefault("max", int(np.max(d))),
                                    stop=lambda: None, wait=lambda: None)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    CV.Player(volume=3.0).play(tmp_path / "a.wav")
    assert got["max"] == 32767


def test_style_references_and_cache_keys(tmp_path):
    from capricorn.tts.capri_voice import CapriVoice
    ref = tmp_path / "capri.wav"
    W.write_wav(ref, np.zeros(24000 * 6, np.float32), 24000)
    W.write_wav(tmp_path / "capri-angry.wav", np.zeros(24000 * 6, np.float32), 24000)
    (tmp_path / "capri-happy.mp3").write_bytes(b"x")
    (tmp_path / "capri.chatterbox-turbo.abc.conds.pt").write_bytes(b"x")
    refs = W.style_references(ref)
    assert set(refs) == {"", "angry", "happy"}
    c = CapriVoice(ref, cmd=["x"], player=FakePlayer())
    assert c.style_ref("angry").name == "capri-angry.wav"
    assert c.style_ref("sad") == ref                                   # no sad recording -> main voice
    assert c.cache_file("Nope.", "angry") != c.cache_file("Nope.", "")
    assert c.cache_file("Nope.", "sad") == c.cache_file("Nope.", "")


def test_recorded_line_keys_ignore_punctuation():
    from capricorn.tts.engine import _key
    assert _key("My brain's offline - is Ollama running?") == _key("My brain's offline. Is Ollama running?")


def test_every_listening_prompt_is_in_a_recording_pack():
    from capricorn import persona
    texts = {t for t, _ in persona.LINES["listening"]}
    assert "Go ahead, choom." in texts and len(texts) >= 4


def test_slang_respelled_for_speech_only():
    parts = textprep.for_speech("Preem choice, choomba. Corpo AV incoming.", "smile")
    joined = " ".join(parts)
    assert "Pream choice" in joined and "choombuh" in joined and "Corpo" in joined and "A V" in joined
    assert textprep.respell("I gonk", {"gonk": "gonnk"}) == "I gonnk"
    assert textprep.respell("preem preemo") == "pream pream-oh"
