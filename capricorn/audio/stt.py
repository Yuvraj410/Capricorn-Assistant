"""Speech-to-text with faster-whisper (free, local). Loaded lazily; falls back to CPU if CUDA fails."""
from __future__ import annotations

import logging
import time
import threading

import numpy as np

from .. import paths
from ..config import Settings

log = logging.getLogger(__name__)


class STT:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._model = None
        self._device = None
        self._lock = threading.Lock()

    def _load(self, force_cpu: bool = False):
        from faster_whisper import WhisperModel  # heavy import, keep lazy

        name = self.s.get("stt.model", "small.en")
        device = "cpu" if force_cpu else str(self.s.get("stt.device", "cpu")).lower()
        compute = str(self.s.get("stt.compute_type", "int8"))
        if device == "auto":
            device = "cuda"
        if device == "cpu" and compute == "float16":
            compute = "int8"
        if device == "cuda" and compute == "int8":
            compute = "int8_float16"
        root = str(paths.models_dir() / "whisper")
        try:
            self._model = WhisperModel(name, device=device, compute_type=compute, download_root=root,
                                       cpu_threads=int(self.s.get("stt.cpu_threads", 4)))
            self._device = device
        except Exception as e:
            if device != "cpu":
                log.warning("Whisper on %s failed (%s) - falling back to CPU", device, e)
                self._model = WhisperModel(name, device="cpu", compute_type="int8", download_root=root,
                                           cpu_threads=int(self.s.get("stt.cpu_threads", 4)))
                self._device = "cpu"
            else:
                raise
        log.info("Whisper %s loaded on %s", name, self._device)

    def reload(self) -> None:
        """New model / device / threads: swap in the background; until then the old one keeps working."""
        def go() -> None:
            old_device = self._device
            try:
                with self._lock:
                    self._model = None
                    self._load()
                log.info("speech recognition reloaded (was %s)", old_device)
            except Exception:
                log.exception("speech recognition reload failed")
        threading.Thread(target=go, daemon=True, name="stt-reload").start()

    def preload(self) -> None:
        t_wait = time.time()
        with self._lock:
            if time.time() - t_wait > 2:
                log.warning("waited %.1fs for the speech recogniser", time.time() - t_wait)
            if self._model is None:
                self._load()

    def transcribe(self, audio_int16: np.ndarray, hotwords: str | None = None) -> str:
        if audio_int16.size < 1600:   # < 0.1 s
            return ""
        audio = audio_int16.astype(np.float32) / 32768.0
        t_wait = time.time()
        with self._lock:
            if time.time() - t_wait > 2:
                log.warning("waited %.1fs for the speech recogniser", time.time() - t_wait)
            if self._model is None:
                self._load()
            try:
                return self._run(audio, hotwords)
            except Exception as e:   # typically a missing CUDA DLL at first use
                if self._device != "cpu":
                    log.warning("Whisper failed on %s (%s) - switching to CPU", self._device, e)
                    self._load(force_cpu=True)
                    return self._run(audio, hotwords)
                raise

    def _run(self, audio: np.ndarray, hotwords: str | None) -> str:
        text = self._decode(audio, hotwords, vad=True)
        if not text and _loud_enough(audio):
            # Silero VAD often throws away very short calls like "Hey C" (it removed the whole
            # clip in testing). There *was* speech energy, so try again without it.
            text = self._decode(audio, hotwords, vad=False)
            log.debug("no-VAD retry heard %r", text)
        return text

    def _decode(self, audio: np.ndarray, hotwords: str | None, vad: bool) -> str:
        kwargs = dict(language="en", beam_size=5, vad_filter=vad, condition_on_previous_text=False)
        if vad:
            kwargs["vad_parameters"] = {"min_silence_duration_ms": 300, "threshold": 0.35,
                                        "min_speech_duration_ms": 120}
        if hotwords:
            kwargs["hotwords"] = hotwords
        try:
            segments, _ = self._model.transcribe(audio, **kwargs)
        except TypeError:          # older faster-whisper without hotwords
            kwargs.pop("hotwords", None)
            segments, _ = self._model.transcribe(audio, **kwargs)
        text = " ".join(s.text.strip() for s in segments).strip()
        return "" if is_hallucination(text) else text


HALLUCINATIONS = {"you", "thanks for watching", "thank you for watching",
                  "thanks for watching!", "please subscribe", "subtitles by the amara.org community", ""}


def is_hallucination(text: str) -> bool:
    """Whisper's classic output on near-silence."""
    return text.lower().strip(" .!?") in HALLUCINATIONS


def _loud_enough(audio: np.ndarray) -> bool:
    """Any 30 ms frame clearly above silence (~-38 dBFS)?"""
    n = 480
    if audio.size < n:
        return False
    frames = audio[: audio.size // n * n].reshape(-1, n)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    return float(rms.max()) > 0.012
