"""Client for Capri's own voice (capricorn.tts.worker running in capricorn-data/voice-env).

* Each reply is split into sentences; every sentence is synthesized separately (and cached on disk),
  so she starts talking after the first sentence instead of after the whole reply.
* A newer reply interrupts an older one (playback stops, queued sentences are skipped).
* Everything degrades quietly: if the voice env is missing or the model fails, replies stay text-only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

from .. import paths
from .worker import MODEL_NAME, style_references

log = logging.getLogger(__name__)
CACHE_LIMIT = 600            # cached sentence clips kept on disk


def read_wav(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        data = np.frombuffer(w.readframes(n), dtype="<i2")
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1).astype("<i2")
    return data, sr


def wav_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as w:
        return int(1000 * w.getnframes() / max(1, w.getframerate()))


class Player:
    """Plays wav files one at a time on the default output device; stop() is immediate.
    `volume` (0.1 - 3.0) scales the audio on top of the loudness the worker already applied."""

    def __init__(self, volume: float = 1.0) -> None:
        self._stop = threading.Event()
        self.volume = volume

    def play(self, path: Path) -> bool:
        """Blocking. Returns False if stopped early."""
        import sounddevice as sd
        import numpy as np
        data, sr = read_wav(path)
        if abs(self.volume - 1.0) > 0.01:
            v = max(0.1, min(3.0, float(self.volume)))
            data = np.clip(data.astype(np.float32) * v, -32767, 32767).astype("<i2")
        self._stop.clear()
        sd.play(data, sr)
        end = time.time() + len(data) / sr + 0.05
        while time.time() < end:
            if self._stop.wait(0.03):
                sd.stop()
                return False
        sd.wait()
        return True

    def stop(self) -> None:
        self._stop.set()


class CapriVoice:
    def __init__(self, reference: Path, python: Optional[Path] = None, device: str = "auto", seed: int = 7,
                 temperature: float = 0.8, loudness: float = -16.0, volume: float = 1.0, on_status: Callable[[str], None] = lambda s: None,
                 cmd: Optional[list[str]] = None, player=None,
                 on_ready: Callable[[], None] = lambda: None) -> None:
        self.reference = Path(reference)
        self.python = Path(python) if python else paths.voice_python()
        self.device, self.seed, self.temperature, self.loudness = device, seed, temperature, loudness
        self.on_status = on_status
        self.on_ready = on_ready
        self._cmd = cmd                      # tests can inject a fake worker
        self.player = player or Player(volume)
        self.proc: Optional[subprocess.Popen] = None
        self.ready = threading.Event()
        self.failed = ""
        self.info: dict = {}
        self._lock = threading.Lock()
        self._next_id = 0
        self.gen = 0
        self._waiting: dict[int, "queue.Queue[dict]"] = {}
        self._crashes = 0
        self._closing = False
        self._play_q: "queue.Queue[tuple]" = queue.Queue()
        self.cache_dir = paths.voice_cache_dir() / "tts"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._playback_loop, daemon=True, name="voice-play").start()

    # -- worker process ---------------------------------------------------------------------------
    @staticmethod
    def installed(python: Optional[Path] = None) -> bool:
        return Path(python or paths.voice_python()).exists()

    def start(self) -> None:
        threading.Thread(target=self._spawn, daemon=True, name="voice-start").start()

    def _spawn(self) -> None:
        if not self.reference.exists():
            self._fail(f"Voice reference missing: {self.reference}")
            return
        cmd = self._cmd or [str(self.python), "-m", "capricorn.tts.worker", "--reference", str(self.reference),
                            "--device", self.device, "--seed", str(self.seed),
                            "--temperature", str(self.temperature), "--loudness", str(self.loudness)]
        logf = open(paths.logs_dir() / "voice.log", "a", encoding="utf-8", errors="replace")
        logf.write(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} starting voice worker\n")
        logf.flush()
        flags = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        try:
            self.proc = subprocess.Popen(cmd, cwd=str(paths.REPO_DIR), stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=logf, env=env, creationflags=flags,
                                         text=True, encoding="utf-8", errors="replace", bufsize=1)
        except OSError as e:
            self._fail(f"Couldn't start Capri's voice: {e}")
            return
        self.on_status("Capri's voice is loading...")
        first = self.proc.stdout.readline()
        try:
            hello = json.loads(first) if first.strip() else {"ready": False, "error": "worker exited"}
        except ValueError:
            hello = {"ready": False, "error": f"bad worker output: {first[:120]}"}
        if not hello.get("ready"):
            self._fail(f"Capri's voice failed to load: {hello.get('error', '?')} (see logs\\voice.log)")
            return
        self.info = hello
        self.failed = ""
        self._crashes = 0
        self.ready.set()
        where = hello.get("gpu") or hello.get("device", "?")
        log.info("voice ready on %s (load %ss + warm-up %ss)", where, hello.get("load_s"), hello.get("warmup_s"))
        self.on_status(f"Capri's voice online ({where})")
        try:
            self.on_ready()
        except Exception:
            log.exception("on_ready failed")
        self._read_loop(self.proc)

    def _read_loop(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            q = self._waiting.pop(msg.get("id"), None)
            if q is not None:
                q.put(msg)
        # worker ended
        self.ready.clear()
        for q in list(self._waiting.values()):
            q.put({"ok": False, "error": "voice worker stopped"})
        self._waiting.clear()
        if self._closing:
            return
        self._crashes += 1
        log.warning("voice worker exited (code %s), crash #%d", proc.poll(), self._crashes)
        if self._crashes <= 2:
            time.sleep(3)
            self._spawn()
        else:
            self._fail("Capri's voice keeps crashing - text only for now (see logs\\voice.log)")

    def _fail(self, msg: str) -> None:
        self.failed = msg
        self.ready.clear()
        log.error(msg)
        self.on_status(msg)

    def close(self) -> None:
        self._closing = True
        self.stop()
        p = self.proc
        if p and p.poll() is None:
            try:
                p.stdin.write('{"cmd": "quit"}\n')
                p.stdin.flush()
                p.wait(2)
            except Exception:
                pass
            if p.poll() is None:
                p.kill()

    # -- speaking ------------------------------------------------------------------------------------
    def style_ref(self, style: str) -> Path:
        """The recording a style will actually use (falls back to the main reference)."""
        refs = getattr(self, "_refs", None)
        if refs is None or time.time() - getattr(self, "_refs_t", 0) > 30:
            refs = style_references(self.reference) if self.reference.exists() else {"": self.reference}
            self._refs, self._refs_t = refs, time.time()
        return refs.get(style) or refs[""]

    def cache_file(self, text: str, style: str = "") -> Path:
        r = self.style_ref(style)
        try:
            st = r.stat()
            ref = f"{r.name}|{st.st_size}|{int(st.st_mtime)}"
        except OSError:
            ref = r.name
        key = hashlib.sha1(f"{MODEL_NAME}|{ref}|{self.seed}|{self.temperature}|{self.loudness}|{text}".encode()).hexdigest()[:20]
        return self.cache_dir / f"{key}.wav"

    def _request(self, text: str, out: Path, gen: int, style: str = "") -> "queue.Queue[dict]":
        q: "queue.Queue[dict]" = queue.Queue(maxsize=1)
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            self._waiting[rid] = q
            try:
                self.proc.stdin.write(json.dumps({"id": rid, "gen": gen, "text": text, "out": str(out),
                                                  "style": style, "seed": self.seed,
                                                  "temperature": self.temperature,
                                                  "loudness": self.loudness}) + "\n")
                self.proc.stdin.flush()
            except Exception as e:
                self._waiting.pop(rid, None)
                q.put({"ok": False, "error": str(e)})
        return q

    def can_speak(self, parts: list[str], style: str = "") -> bool:
        """Ready, or every sentence is already cached."""
        return self.ready.is_set() or (bool(parts) and all(self.cache_file(p, style).exists() for p in parts))

    def speak(self, parts: list[str], on_chunk: Callable[[int], None], on_done: Callable[[bool], None],
              style: str = "") -> bool:
        """Queue sentences for synthesis + playback. Returns False if nothing will be said.
        on_chunk(ms) fires as each sentence starts playing; on_done(completed) once at the end."""
        if not parts or not self.can_speak(parts, style):
            return False
        self.stop()
        self._last_speak = time.time()
        with self._lock:
            self.gen += 1
            gen = self.gen
        items = []
        for p in parts:
            f = self.cache_file(p, style)
            if f.exists():
                try:
                    os.utime(f)              # keep recently used clips when pruning
                except OSError:
                    pass
                items.append((p, f, None))
            elif self.ready.is_set():
                items.append((p, f, self._request(p, f, gen, style)))
        self._play_q.put((gen, items, on_chunk, on_done))
        return True

    def stop(self) -> None:
        with self._lock:
            self.gen += 1
        self.player.stop()

    def prewarm(self, items: list[tuple[str, str]]) -> None:
        """Make clips for (text, style) pairs in the background, one at a time, only while Capri is
        idle - real replies always go first. Already-cached clips are skipped."""
        def run() -> None:
            if not self.ready.wait(600):
                return
            made = 0
            for text, style in items:
                f = self.cache_file(text, style)
                for _ in range(20):                  # wait for a quiet moment
                    if f.exists() or self._closing:
                        break
                    if time.time() - getattr(self, "_last_speak", 0) > 8 and self._play_q.empty():
                        try:
                            msg = self._request(text, f, self.gen, style).get(timeout=60) if self.ready.is_set() else {}
                        except queue.Empty:
                            msg = {}
                        if msg.get("ok"):
                            made += 1
                            break
                    time.sleep(3)
                if self._closing or not self.ready.is_set():
                    return
            if made:
                log.info("voice: pre-made %d lines", made)
        threading.Thread(target=run, daemon=True, name="voice-prewarm").start()

    def _playback_loop(self) -> None:
        while True:
            gen, items, on_chunk, on_done = self._play_q.get()
            completed = True
            for text, f, q in items:
                if gen != self.gen:
                    completed = False
                    break
                if q is not None:
                    try:
                        msg = q.get(timeout=60)
                    except queue.Empty:
                        msg = {"ok": False, "error": "timeout"}
                    if not msg.get("ok"):
                        if not msg.get("skipped"):
                            log.warning("voice: %s", msg.get("error"))
                        completed = False
                        break
                    log.info("voice: %.2fs for %r", msg.get("took", 0), text[:60])
                if gen != self.gen or not f.exists():
                    completed = False
                    break
                try:
                    on_chunk(wav_ms(f))
                    if not self.player.play(f):
                        completed = False
                        break
                except Exception:
                    log.exception("voice playback failed")
                    completed = False
                    break
            try:
                on_done(completed)
            except Exception:
                log.exception("voice on_done failed")
            self._prune()

    def _prune(self) -> None:
        try:
            files = sorted(self.cache_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime)
            for p in files[:-CACHE_LIMIT]:
                p.unlink(missing_ok=True)
        except OSError:
            pass
