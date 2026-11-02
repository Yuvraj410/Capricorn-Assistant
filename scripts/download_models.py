"""Downloads the free models Capricorn needs into capricorn-data\\models.

  * Vosk small English model (~40 MB) - always-on wake-word spotting
  * faster-whisper model (small.en, ~480 MB) - speech-to-text
Run by Setup.exe; safe to run again (skips what's already there).
"""
from __future__ import annotations

import os
import sys
import tempfile
import warnings
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows without Developer Mode can't make symlinks; Hugging Face then just copies files.
# That's fine - hide the scary-looking warnings about it.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
warnings.filterwarnings("ignore", message=".*symlinks.*")
warnings.filterwarnings("ignore", message=".*unauthenticated.*")

from capricorn import paths  # noqa: E402
from capricorn.audio.listener import VOSK_MODEL_NAME, find_vosk_model  # noqa: E402
from capricorn.config import Settings, ensure_user_files  # noqa: E402

VOSK_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_NAME}.zip"


def _progress(block, bsize, total):
    if total > 0:
        pct = min(100, block * bsize * 100 // total)
        print(f"\r    {pct:3d}%", end="", flush=True)


def get_vosk() -> None:
    if find_vosk_model():
        print("[ OK ] Wake-word model already installed")
        return
    print(f"[....] Downloading wake-word model ({VOSK_MODEL_NAME}, ~40 MB)")
    tmp = Path(tempfile.gettempdir()) / f"{VOSK_MODEL_NAME}.zip"
    urllib.request.urlretrieve(VOSK_URL, tmp, _progress)
    print()
    with zipfile.ZipFile(tmp) as z:
        z.extractall(paths.models_dir())
    tmp.unlink(missing_ok=True)
    print("[ OK ] Wake-word model installed")


def get_whisper() -> None:
    s = Settings()
    name = s.get("stt.model", "small.en")
    root = str(paths.models_dir() / "whisper")
    print(f"[....] Downloading speech-to-text model (whisper {name}, ~480 MB) - this can take a few minutes")
    try:  # download with a visible progress bar (faster-whisper hides it)
        from faster_whisper.utils import _MODELS
        from huggingface_hub import snapshot_download
        repo = _MODELS.get(name, name)
        snapshot_download(repo, cache_dir=root,
                          allow_patterns=["config.json", "preprocessor_config.json", "model.bin",
                                          "tokenizer.json", "vocabulary.*"])
    except Exception as e:
        print(f"       (progress bar unavailable: {e.__class__.__name__}) - downloading quietly...")
    from faster_whisper import WhisperModel
    WhisperModel(name, device="cpu", compute_type="int8", download_root=root)   # verifies it loads
    print("[ OK ] Speech-to-text model ready")


if __name__ == "__main__":
    ensure_user_files()
    try:
        get_vosk()
        get_whisper()
    except Exception as e:
        print(f"\n[FAIL] Model download failed: {e}")
        print("       Check your internet connection and run Setup.exe again.")
        sys.exit(1)
