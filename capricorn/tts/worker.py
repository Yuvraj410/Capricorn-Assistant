"""Capri's voice worker - runs in the separate voice environment (capricorn-data/voice-env),
which has PyTorch + Chatterbox Turbo (MIT licence, zero-shot voice cloning from a short clip).

The app starts it with:  voice-env/python -m capricorn.tts.worker --reference voices/capri.wav
and talks to it with JSON lines (stdout carries ONLY protocol lines; library noise goes to stderr):
    -> {"id": 3, "gen": 2, "text": "Lo-fi's queued, choom.", "out": "C:/.../x.wav"}
    <- {"id": 3, "ok": true, "file": "C:/.../x.wav", "ms": 1840, "took": 0.62}
    <- {"id": 4, "skipped": true}            (an older reply was interrupted by a newer one)
First line: {"ready": true, "device": "cuda", "gpu": "...", "sr": 24000, "load_s": 9.1}
         or {"ready": false, "error": "..."}

Self-test (used by the installer):  ... -m capricorn.tts.worker --reference X --selftest out.wav
Only needs the standard library + torch/chatterbox, never the app's own packages (Qt, yaml...).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import logging
import os
import sys
import threading
import time
import wave
from pathlib import Path

from .. import paths

log = logging.getLogger("capricorn.voice")
MODEL_NAME = "chatterbox-turbo"


def _protocol_stdout():
    """Keep a private handle on the real stdout and point fd 1 at stderr, so prints from
    torch/transformers/C code can never corrupt the protocol stream."""
    out = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    try:
        os.dup2(2, 1)
    except OSError:
        pass
    sys.stdout = sys.stderr
    return out


def _setup_env() -> None:
    hf = paths.models_dir() / "hf"
    os.environ.setdefault("HF_HOME", str(hf))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)-7s voice: %(message)s")


def pick_device(torch, want: str = "auto") -> str:
    if want == "cpu":
        return "cpu"
    if torch.cuda.is_available():
        try:   # an old PyTorch can "see" a new GPU but have no kernels for it (RTX 50xx needs cu128+)
            (torch.ones(8, device="cuda") * 2).sum().item()
            return "cuda"
        except Exception as e:
            log.warning("CUDA present but unusable (%s) - using CPU", e)
    elif want == "cuda":
        log.warning("CUDA requested but not available - using CPU")
    return "cpu"


AUDIO_EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a")


def style_references(reference: Path) -> dict[str, Path]:
    """voices/capri.wav + voices/capri-happy.wav, capri-angry.mp3 ... -> {"": main, "happy": ..., ...}.
    Each mood recording makes that mood's lines sound like it (zero-shot cloning copies delivery too)."""
    out = {"": reference}
    for p in sorted(reference.parent.glob(f"{reference.stem}-*")):
        if p.suffix.lower() in AUDIO_EXT and not p.name.endswith(".conds.pt"):
            style = p.stem[len(reference.stem) + 1:].lower()
            if style and style.isalpha():
                out.setdefault(style, p)
    return out


def conds_path(reference: Path) -> Path:
    st = reference.stat()
    tag = hashlib.sha1(f"{MODEL_NAME}|{reference.name}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:10]
    return reference.with_name(f"{reference.stem}.{MODEL_NAME}.{tag}.conds.pt")


def normalize(samples, sr: int, target_lufs: float = -16.0):
    """Chatterbox output is quiet (~-27 LUFS). Bring it to a normal speaking level
    (-16 LUFS is roughly what YouTube / podcasts use), with a peak limit so it never clips."""
    import numpy as np
    a = np.asarray(samples, dtype=np.float32).reshape(-1)
    if a.size < sr // 2 or not np.any(a):
        return a
    try:
        import pyloudnorm as pyln
        loud = pyln.Meter(sr).integrated_loudness(a)
        if np.isfinite(loud):
            a = a * float(10 ** ((target_lufs - loud) / 20))
    except Exception:            # very short clips: fall back to peak normalising
        peak = float(np.max(np.abs(a)))
        if peak > 0:
            a = a * (0.7 / peak)
    # soft limiter: untouched below 0.8, smoothly squeezed above so peaks stay under 0.98
    mag = np.abs(a)
    over = mag > 0.8
    if np.any(over):
        a = np.where(over, np.sign(a) * (0.8 + 0.18 * np.tanh((mag - 0.8) / 0.18)), a).astype(np.float32)
    return a


def write_wav(path: Path, samples, sr: int) -> int:
    import numpy as np
    a = np.asarray(samples, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak > 0.99:
        a = a * (0.99 / peak)
    pcm = (a * 32767.0).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    os.replace(tmp, path)
    return int(1000 * a.size / sr)


class Voice:
    def __init__(self, reference: Path, device: str = "auto", seed: int = 7, temperature: float = 0.8,
                 loudness: float = -16.0) -> None:
        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS, Conditionals
        self.torch = torch
        self.seed = seed
        self.temperature = temperature
        self.loudness = loudness
        t0 = time.time()
        self.device = pick_device(torch, device)
        self.model = ChatterboxTurboTTS.from_pretrained(device=self.device)
        self.styles: dict[str, object] = {}
        for style, ref in style_references(reference).items():
            try:
                self.styles[style] = self._load_conds(ref, Conditionals)
            except Exception:
                if not style:
                    raise
                log.exception("mood recording %s unusable - skipped", ref.name)
        self.model.conds = self.styles[""]
        self.sr = int(self.model.sr)
        self.load_s = round(time.time() - t0, 1)
        self.gpu = torch.cuda.get_device_name(0) if self.device == "cuda" else ""

    def _load_conds(self, ref: Path, Conditionals):
        cp = conds_path(ref)
        if cp.exists():
            log.info("voice %s loaded from cache", ref.name)
            return Conditionals.load(cp, map_location=self.device).to(self.device)
        log.info("analysing reference voice %s (one time)", ref.name)
        self.model.prepare_conditionals(str(ref))
        try:
            self.model.conds.save(cp)
        except Exception:
            log.exception("couldn't cache the voice")
        return self.model.conds

    def say(self, text: str, out: Path, style: str = "", seed: int | None = None,
            temperature: float | None = None, loudness: float | None = None) -> int:
        self.model.conds = self.styles.get(style) or self.styles[""]
        torch = self.torch
        seed = self.seed if seed is None else int(seed)
        if seed >= 0:
            torch.manual_seed(seed)
        with torch.inference_mode():
            wav = self.model.generate(text, temperature=self.temperature if temperature is None else float(temperature))
        lufs = self.loudness if loudness is None else float(loudness)
        return write_wav(out, normalize(wav.squeeze(0).cpu().numpy(), self.sr, lufs), self.sr)


def serve(voice, inp, out) -> None:
    """Read requests on a thread so newer replies can cancel queued older ones."""
    pending: collections.deque = collections.deque()
    cv = threading.Condition()
    latest = {"gen": -1}
    done = {"eof": False}

    def reader() -> None:
        for line in inp:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except ValueError:
                continue
            with cv:
                if req.get("cmd") == "quit":
                    done["eof"] = True
                else:
                    latest["gen"] = max(latest["gen"], int(req.get("gen", 0)))
                    pending.append(req)
                cv.notify()
            if done["eof"]:
                break
        with cv:
            done["eof"] = True
            cv.notify()

    threading.Thread(target=reader, daemon=True, name="voice-stdin").start()
    while True:
        with cv:
            while not pending and not done["eof"]:
                cv.wait()
            if not pending and done["eof"]:
                return
            req = pending.popleft()
            stale = int(req.get("gen", 0)) < latest["gen"]
        rid = req.get("id")
        if stale:
            out.write(json.dumps({"id": rid, "skipped": True}) + "\n")
            continue
        t0 = time.time()
        try:
            ms = voice.say(str(req["text"]), Path(req["out"]), str(req.get("style") or ""),
                           req.get("seed"), req.get("temperature"), req.get("loudness"))
            msg = {"id": rid, "ok": True, "file": req["out"], "ms": ms, "took": round(time.time() - t0, 2)}
        except Exception as e:
            log.exception("synthesis failed for %r", req.get("text"))
            msg = {"id": rid, "ok": False, "error": str(e)[:300]}
        out.write(json.dumps(msg) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="capricorn.tts.worker")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--loudness", type=float, default=-16.0, help="target loudness in LUFS (-23 quiet .. -12 loud)")
    ap.add_argument("--selftest", metavar="OUT_WAV", help="say one test line into OUT_WAV and exit")
    ap.add_argument("--text", default="Hey, choom. Voice module's online. Preem, right?")
    a = ap.parse_args(argv)
    out = _protocol_stdout()
    _setup_env()
    ref = Path(a.reference)
    if not ref.exists():
        out.write(json.dumps({"ready": False, "error": f"reference voice not found: {ref}"}) + "\n")
        return 2
    try:
        voice = Voice(ref, a.device, a.seed, a.temperature, a.loudness)
    except Exception as e:
        log.exception("voice model failed to load")
        out.write(json.dumps({"ready": False, "error": f"{type(e).__name__}: {e}"[:400]}) + "\n")
        return 1
    hello = {"ready": True, "device": voice.device, "gpu": voice.gpu, "sr": voice.sr,
             "load_s": voice.load_s, "styles": sorted(s for s in voice.styles if s)}
    if a.selftest:
        out.write(json.dumps(hello) + "\n")
        t0 = time.time()
        try:
            ms = voice.say(a.text, Path(a.selftest))
        except Exception as e:
            log.exception("self-test failed")
            out.write(json.dumps({"selftest": False, "error": f"{type(e).__name__}: {e}"[:400]}) + "\n")
            return 1
        out.write(json.dumps({"selftest": True, "file": a.selftest, "ms": ms,
                              "took": round(time.time() - t0, 2)}) + "\n")
        return 0
    # warm-up BEFORE announcing ready: the first generation on a GPU takes ~15 s (kernel setup),
    # and a real reply queued behind it would lag by that much.
    t0 = time.time()
    try:
        voice.say("Online.", paths.voice_cache_dir() / "tts" / "_warmup.wav")
        log.info("warm-up took %.1fs on %s", time.time() - t0, voice.device)
    except Exception:
        log.exception("warm-up failed")
    hello["warmup_s"] = round(time.time() - t0, 1)
    out.write(json.dumps(hello) + "\n")
    serve(voice, sys.stdin, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
