"""Always-on microphone listener.

    mic (16 kHz) ──► Vosk, restricted to the wake words (tiny, CPU, ~1-3 %)
                        │ heard "capri"/"capricorn"?
                        ▼
                 the whole sentence (kept in a rolling buffer) ──► Whisper
                        │  "hey capri, open youtube" → command "open youtube"
                        │  "hey capri"               → listen for the command next
                        ▼
                 callbacks into the app (on_wake, on_command, ...)

Runs in its own thread; callbacks are called from that thread (the app re-emits them as Qt signals).
"""
from __future__ import annotations

import collections
import json
import logging
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .. import paths
from ..config import Settings
from .stt import STT
from .wake import WakeMatcher

log = logging.getLogger(__name__)

RATE = 16000
BLOCK = 1600            # 100 ms
MAX_UTTERANCE_S = 15
MAX_COMMAND_S = 12          # hard cap for one command recording
# "uh...", "um, so", "hmm" - the user is still thinking, not done
FILLER = re.compile(r"^(?:(?:uh+|um+|uhm+|erm*|er+|ah+|hm+|mm+|so+|well|like|okay so|ok so|wait|let me think|"
                    r"let's see|lemme think|and|the)[\s,.!?…-]*)+$", re.I)


def is_filler(text: str) -> bool:
    t = text.strip(" .,!?…-")
    return not t or bool(FILLER.match(t))
VAD_EVERY = 4               # run the speech detector every N audio blocks
VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"


@dataclass
class Callbacks:
    on_wake: Callable[[], None] = lambda: None                     # wake word heard (show Capri)
    on_wake_cancel: Callable[[], None] = lambda: None              # false alarm
    on_listening: Callable[[], None] = lambda: None                # waiting for the command
    on_transcribing: Callable[[], None] = lambda: None
    on_command: Callable[[str, str], None] = lambda cmd, heard: None
    on_no_command: Callable[[], None] = lambda: None
    on_capture: Callable[[str, str], None] = lambda kind, text: None   # answer to request_capture()
    on_status: Callable[[str], None] = lambda msg: None
    on_error: Callable[[str], None] = lambda msg: None


def find_vosk_model() -> Optional[str]:
    for base in (paths.models_dir(), paths.REPO_DIR / "models"):
        p = base / VOSK_MODEL_NAME
        if (p / "am").exists() or (p / "conf").exists():
            return str(p)
    return None


class Listener:
    def __init__(self, settings: Settings, stt: STT, cb: Callbacks) -> None:
        self.s = settings
        self.stt = stt
        self.cb = cb
        self.q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=600)
        self.muted = False
        self.speaking = False           # Capri's own voice is playing: don't listen to ourselves
        self._speak_tok = 0
        self.busy = False               # app is showing/handling a reply; wake still works
        self._stop = threading.Event()
        self._capture_kind: Optional[str] = None
        self._capture_timeout = 6.0
        self._thread: Optional[threading.Thread] = None
        self._stream = None
        self.noise = 200.0
        self.hotwords_fn: Callable[[], str] = lambda: "Hey C, Capri, Capricorn, Capricon"
        self._rebuild = self._reopen = False
        self._build_matcher()

    def _build_matcher(self) -> None:
        s = self.s
        self.matcher = WakeMatcher(s.get("wake.words", ["capri", "capricorn", "capricon"]),
                                   s.get("wake.aliases", []),
                                   short_forms=s.get("wake.short_words", []))

    def reconfigure(self, changed: set[str]) -> None:
        """Apply wake settings live: new wake words rebuild the spotter, a new mic reopens the stream.
        Thresholds and timings are read fresh every time anyway."""
        if changed & {"wake.words", "wake.aliases", "wake.short_words"}:
            self._build_matcher()
            self._rebuild = True
        if "wake.input_device" in changed:
            self._reopen = True
        if "wake.enabled" in changed:
            self.cb.on_status("Listening for 'Hey Capri'" if self.s.get("wake.enabled", True)
                              else "Voice wake-up disabled in settings")

    # -- public --------------------------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="listener")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        self._drain()

    def request_capture(self, kind: str, timeout: float = 6.0) -> None:
        """Record the next thing the user says (no wake word needed), e.g. a yes/no answer."""
        self._capture_timeout = timeout
        self._capture_kind = kind

    # -- internals -----------------------------------------------------------------------
    def hold_speaking(self) -> None:
        self._speak_tok += 1
        self.speaking = True

    def release_speaking(self, delay: float = 0.25) -> None:
        """Start listening again `delay` s after the voice stops (room echo)."""
        self._speak_tok += 1
        tok = self._speak_tok

        def go() -> None:
            if tok == self._speak_tok:
                self.speaking = False
                self._drain()
        if delay <= 0:
            go()
        else:
            t = threading.Timer(delay, go)
            t.daemon = True
            t.start()

    def _audio_cb(self, indata, frames, t, status) -> None:  # sounddevice thread
        if self.muted or self.speaking:
            return
        try:
            self.q.put_nowait(indata[:, 0].copy() if indata.ndim > 1 else indata.copy())
        except queue.Full:
            pass

    def _drain(self) -> None:
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    def _open_stream(self) -> bool:
        import sounddevice as sd
        dev = self.s.get("wake.input_device", None)
        try:
            self._stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                          device=dev, callback=self._audio_cb)
            self._stream.start()
            return True
        except Exception as e:
            log.exception("microphone open failed")
            self.cb.on_error(f"Can't open the microphone ({e}). Check Windows privacy settings > Microphone.")
            return False

    def _make_recognizer(self, model):
        from vosk import KaldiRecognizer
        grammar = json.dumps(self.matcher.vosk_vocab() + ["[unk]"])
        rec = KaldiRecognizer(model, RATE, grammar)
        rec.SetWords(True)
        return rec

    def _run(self) -> None:
        try:
            from vosk import Model, SetLogLevel
        except ImportError:
            self.cb.on_error("Voice wake-up needs the 'vosk' package - run Setup.exe again.")
            return
        mpath = find_vosk_model()
        if not mpath:
            self.cb.on_error("Wake-word model missing - run Setup.exe again. (Typed chat still works: Ctrl+Alt+C)")
            return
        SetLogLevel(-1)
        model = Model(mpath)
        rec = self._make_recognizer(model)
        if not self._open_stream():
            return
        self.cb.on_status("Listening for 'Hey Capri'" if self.s.get("wake.enabled", True)
                          else "Voice wake-up disabled in settings")
        utter: collections.deque[np.ndarray] = collections.deque(maxlen=int(MAX_UTTERANCE_S * RATE / BLOCK))
        early = False
        while not self._stop.is_set():
            # settings changed while running (no restart needed)
            if self._rebuild:
                self._rebuild = False
                rec = self._make_recognizer(model)
                utter.clear()
                log.info("wake words updated: %s", ", ".join(self.matcher.vosk_vocab()))
            if self._reopen:
                self._reopen = False
                try:
                    if self._stream is not None:
                        self._stream.stop()
                        self._stream.close()
                except Exception:
                    pass
                self._open_stream()
                log.info("microphone reopened (%s)", self.s.get("wake.input_device", None) or "default")
            if not self.s.get("wake.enabled", True) and not self._capture_kind:
                self._drain()
                time.sleep(0.3)
                continue
            if self._capture_kind:
                kind, self._capture_kind = self._capture_kind, None
                self._drain()
                audio = self._record_command(self._capture_timeout)
                text = self.stt.transcribe(audio, hotwords=self._hotwords()) if audio is not None else ""
                if text:
                    found, rest = self.matcher.find(text)       # "Capri, yes" -> "yes"
                    if found:
                        text = rest
                log.info("%s reply: %r", kind, text)
                self.cb.on_capture(kind, text)
                rec.Reset(); utter.clear(); self._drain()
                continue
            try:
                block = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            utter.append(block)
            self._update_noise(block)
            if rec.AcceptWaveform(block.tobytes()):
                res = json.loads(rec.Result() or "{}")
                text = res.get("text", "")
                audio = np.concatenate(list(utter)) if utter else np.zeros(0, np.int16)
                utter.clear()
                if self._vosk_wake(res):
                    if not early:
                        self.cb.on_wake()
                    early = False
                    # Vosk ends utterances at very short pauses ("play... my liked music"):
                    # keep listening briefly in case the sentence continues.
                    t_rec = time.time()
                    more = self._record_until_pause(start_wait=0.8)
                    if more.size:
                        audio = np.concatenate([audio, more])
                    log.info("wake audio %.1fs (recorded for %.1fs)", audio.size / RATE, time.time() - t_rec)
                    self._handle_wake(audio)
                    rec.Reset(); utter.clear(); self._drain()
                elif not early and self._vosk_maybe_short(res):
                    log.info("vosk maybe short wake %r - checking quietly", text)
                    more = self._record_until_pause(start_wait=0.8)
                    if more.size:
                        audio = np.concatenate([audio, more])
                    self._handle_wake(audio, quiet=True)
                    rec.Reset(); utter.clear(); self._drain()
                elif early:
                    early = False
                    self.cb.on_wake_cancel()
                log.debug("vosk final: %r", text)
            else:
                partial = json.loads(rec.PartialResult() or "{}").get("partial", "")
                if not early and partial and self._has_wake_token(partial):
                    self.cb.on_wake()
                    # Don't wait for Vosk's (too eager) end of utterance - record until the user
                    # has actually stopped talking, then transcribe the whole sentence.
                    rest = self._record_until_pause()
                    audio = np.concatenate(list(utter) + ([rest] if rest.size else []))
                    utter.clear()
                    self._handle_wake(audio)
                    rec.Reset(); utter.clear(); self._drain()
                    early = False

    def _hotwords(self) -> str:
        try:
            return self.hotwords_fn()
        except Exception:
            return "Hey C, Capri, Capricorn, Capricon"

    def _has_wake_token(self, text: str) -> bool:
        # early "Listening..." only for the long wake words - "see" is far too common for that
        toks = [t for t in text.split() if t not in {"[unk]", "hey", "okay"} and t not in self.matcher.short]
        return bool(toks)

    def _vosk_wake(self, res: dict) -> bool:
        seq = [w.get("word") for w in res.get("result", [])]
        words = [w for w in res.get("result", []) if w.get("word") not in {"[unk]", "hey", "okay"}]
        if not words:
            return False
        long_words = [w for w in words if w.get("word") not in self.matcher.short]
        if not long_words:
            # short wake word ("see"): only at the very start, or right after "hey"/"okay"
            i = next((k for k, w in enumerate(seq) if w in self.matcher.short), -1)
            ok = i == 0 or (i > 0 and seq[i - 1] in {"hey", "okay"})
            log.info("vosk short wake %r -> %s", seq, ok)
            if not ok:
                return False
        return max(float(w.get("conf", 1.0)) for w in words) >= float(self.s.get("wake.min_confidence", 0.55))

    def _vosk_maybe_short(self, res: dict) -> bool:
        """'[unk] see ...' - Vosk often hears "hey" as [unk]. Could be "Hey C" or just "I see";
        worth a silent Whisper check (no pop-up unless Whisper confirms)."""
        seq = [w.get("word") for w in res.get("result", [])]
        return len(seq) >= 2 and seq[0] == "[unk]" and seq[1] in self.matcher.short

    def _update_noise(self, block: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(block.astype(np.float32) ** 2))) if block.size else 0.0
        if rms < self.noise * 2.0:
            self.noise = 0.97 * self.noise + 0.03 * max(rms, 30.0)

    def _handle_wake(self, audio: np.ndarray, quiet: bool = False) -> None:
        heard = ""
        if quiet or self.s.get("wake.verify_with_whisper", True):
            if not quiet:
                self.cb.on_transcribing()
            try:
                heard = self.stt.transcribe(audio, hotwords=self._hotwords())
            except Exception as e:
                log.exception("transcription failed")
                self.cb.on_error(f"Speech recognition failed: {e}")
                return
            found, command = self.matcher.find(heard)
            log.info("wake utterance: %r -> found=%s command=%r", heard, found, command)
            if not found:
                if not quiet:
                    self.cb.on_wake_cancel()
                return
            if quiet:
                self.cb.on_wake()
        else:
            command = ""
        if len(command.strip(" .,!?")) >= 2 and not is_filler(command):
            self.cb.on_command(command, heard)
            return
        # Bare "Hey Capri" -> wait for the command
        self.cb.on_listening()
        cmd_audio = self._record_command(float(self.s.get("wake.command_timeout", 6.0)))
        if cmd_audio is not None:   # the user may pause mid-command too
            more = self._record_until_pause(start_wait=0.6)
            if more.size:
                cmd_audio = np.concatenate([cmd_audio, more])
        if cmd_audio is None:
            self.cb.on_no_command()
            return
        self.cb.on_transcribing()
        try:
            text = self.stt.transcribe(cmd_audio, hotwords=self._hotwords())
        except Exception as e:
            log.exception("transcription failed")
            self.cb.on_error(f"Speech recognition failed: {e}")
            return
        log.info("command utterance: %r", text)
        tries = 0
        while is_filler(text) and tries < 2:          # "uh..." - still thinking: keep listening
            tries += 1
            more = self._record_command(float(self.s.get("wake.command_timeout", 6.0)) + 2)
            if more is None:
                break
            extra = self.stt.transcribe(more, hotwords=self._hotwords())
            log.info("command utterance (after a pause): %r", extra)
            text = extra if is_filler(text) else f"{text} {extra}"
        found, rest = self.matcher.find(text)   # people often repeat "Capri, ..."
        text = rest if found and rest else text
        if text.strip(" .,!?"):
            self.cb.on_command(text, text)
        else:
            self.cb.on_no_command()

    def _speech_ended(self, got: list[np.ndarray], end_sil: float) -> bool:
        """Silero VAD (ships with faster-whisper) on the last `end_sil` seconds: no speech in there ->
        the user has finished. Energy alone can't tell a voice from music or a show playing in the
        background, so with media on, recordings used to run to the time limit."""
        if getattr(self, "_vad_broken", False):
            return False
        n = int(end_sil * RATE)
        if sum(b.size for b in got) < n + RATE // 2:
            return False
        tail = np.concatenate(got[-(n // BLOCK + 2):])[-n:].astype(np.float32) / 32768.0
        try:
            from faster_whisper.vad import VadOptions, get_speech_timestamps
            ts = get_speech_timestamps(tail, VadOptions(threshold=0.55, min_speech_duration_ms=200,
                                                        min_silence_duration_ms=150))
        except Exception:
            log.warning("speech detector unavailable - using loudness only", exc_info=True)
            self._vad_broken = True
            return False
        return not ts

    def _record_until_pause(self, start_wait: Optional[float] = None) -> np.ndarray:
        """Record until `end_silence` seconds of quiet.
        start_wait=None: speech is already in progress. Otherwise wait up to start_wait seconds
        for speech to (re)start and return an empty array if it doesn't."""
        end_sil = float(self.s.get("wake.end_silence", 1.2))
        got: list[np.ndarray] = []
        started = start_wait is None
        quiet, loud_run, t0 = 0.0, 0, time.time()
        vad_tick = 0
        while not self._stop.is_set():
            try:
                block = self.q.get(timeout=0.3)
            except queue.Empty:
                if not started and time.time() - t0 > (start_wait or 0):
                    break
                if started:
                    quiet += 0.3
                    if quiet >= end_sil:
                        break
                continue
            rms = float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))
            thr = max(self.noise * 3.0, 160.0)
            if not started:
                got.append(block)
                loud_run = loud_run + 1 if rms > thr else 0
                if loud_run >= 2:
                    started = True
                elif time.time() - t0 > (start_wait or 0):
                    break
                continue
            got.append(block)
            quiet = quiet + BLOCK / RATE if rms <= thr else 0.0
            if quiet >= end_sil or len(got) * BLOCK / RATE > MAX_COMMAND_S:
                break
            vad_tick += 1
            if vad_tick % VAD_EVERY == 0 and self._speech_ended(got, end_sil):
                log.debug("speech ended (VAD)")
                break
        if not started or not got:
            return np.zeros(0, np.int16)
        return np.concatenate(got)

    def _record_command(self, start_timeout: float) -> Optional[np.ndarray]:
        """Energy-based recording: wait for speech, stop after `end_silence` seconds of quiet."""
        end_sil = float(self.s.get("wake.end_silence", 1.2))
        pre: collections.deque[np.ndarray] = collections.deque(maxlen=4)
        got: list[np.ndarray] = []
        started, loud_run, quiet = False, 0, 0.0
        vad_tick = 0
        t0 = time.time()
        while not self._stop.is_set():
            try:
                block = self.q.get(timeout=0.3)
            except queue.Empty:
                if not started and time.time() - t0 > start_timeout:
                    return None
                continue
            rms = float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))
            thr = max(self.noise * 3.0, 160.0)
            if not started:
                pre.append(block)
                loud_run = loud_run + 1 if rms > thr else 0
                if loud_run >= 2:
                    started = True
                    got.extend(pre)
                elif time.time() - t0 > start_timeout:
                    return None
                else:
                    self._update_noise(block)
                continue
            got.append(block)
            quiet = quiet + BLOCK / RATE if rms <= thr else 0.0
            if quiet >= end_sil or len(got) * BLOCK / RATE > MAX_COMMAND_S:
                break
            vad_tick += 1
            if vad_tick % VAD_EVERY == 0 and self._speech_ended(got, end_sil):
                log.debug("speech ended (VAD)")
                break
        return np.concatenate(got) if got else None
