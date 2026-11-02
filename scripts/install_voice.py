"""Installs Capri's own voice: a separate Python environment (capricorn-data\\voice-env) with
PyTorch + Chatterbox Turbo, downloads the model (~1.5 GB, one time), checks the reference recording,
says a test line and switches voice.engine to "capri". Free, runs locally, no account needed.

Run through commands\\install-capri-voice.bat (uses the app's Python environment):
    capricorn-data\\python\\Scripts\\python.exe scripts\\install_voice.py [--cpu] [--reference FILE] [--reinstall]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capricorn import paths  # noqa: E402

TORCH = ["torch==2.8.0", "torchaudio==2.8.0"]
CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"
CHATTERBOX = "chatterbox-tts==0.1.7"


def say(tag: str, msg: str) -> None:
    print(f"[{tag:^4}] {msg}", flush=True)


def run(cmd: list[str], what: str) -> None:
    say("....", what)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        say("FAIL", f"{what} failed (exit {r.returncode}). Check your internet connection and run this again.")
        sys.exit(1)


def base_python() -> str:
    """The Python that created the app's environment (pyvenv.cfg 'home')."""
    cfg = paths.user_dir() / "python" / "pyvenv.cfg"
    if cfg.exists():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            k, _, v = line.partition("=")
            if k.strip().lower() == "home":
                exe = Path(v.strip()) / ("python.exe" if sys.platform == "win32" else "python3")
                if exe.exists():
                    return str(exe)
    return getattr(sys, "_base_executable", sys.executable)


def has_nvidia() -> bool:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return False
    try:
        return subprocess.run([smi, "-L"], capture_output=True, timeout=15).returncode == 0
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true", help="install the CPU build even if there's an NVIDIA GPU")
    ap.add_argument("--reference", help="audio file of the voice to clone (10-20 s, clean, one speaker)")
    ap.add_argument("--reinstall", action="store_true", help="delete and recreate the voice environment")
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--no-play", action="store_true", help="make the test line but don't play it (installer)")
    a = ap.parse_args()

    print("\n   CAPRI'S VOICE  //  local voice cloning (Chatterbox Turbo, MIT licence)\n")
    env = paths.voice_env_dir()
    vpy = paths.voice_python()

    # 1. reference recording
    voices = paths.voices_dir()
    ref = voices / "capri.wav"
    bundled = paths.REPO_DIR / "reference-voices" / "capri.wav"
    source = a.reference or (str(bundled) if not ref.exists() and bundled.is_file() else None)
    if source:
        src = Path(source).expanduser()
        if not src.exists():
            say("FAIL", f"Reference file not found: {src}")
            return 1
        ref = voices / f"capri{src.suffix.lower()}"
        if src.resolve() != ref.resolve():
            shutil.copyfile(src, ref)
        # Only copy named delivery samples, never the long packs of recorded lines.
        for style in ("happy", "playful", "sad", "surprised", "angry", "calm"):
            for ext in (".wav", ".mp3", ".flac", ".ogg"):
                mood = src.with_name(f"{src.stem}-{style}{ext}")
                if mood.is_file():
                    dst = voices / f"{ref.stem}-{style}{ext}"
                    if mood.resolve() != dst.resolve():
                        shutil.copyfile(mood, dst)
                    break
        say(" OK ", f"Reference voice copied to {ref}")
    if not ref.exists():
        say("FAIL", f"No reference recording. Put a clean 10-20 second clip of the voice at\n         {ref}\n"
                    "         (or run again with --reference \"C:\\path\\to\\clip.wav\")")
        return 1

    # 2. environment
    if a.reinstall and env.exists():
        say("....", "Removing the old voice environment")
        shutil.rmtree(env, ignore_errors=True)
    if not vpy.exists():
        run([base_python(), "-m", "venv", str(env)], f"Creating the voice environment in {env}")
    run([str(vpy), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], "Updating pip")

    gpu = has_nvidia() and not a.cpu
    index = CUDA_INDEX if gpu else CPU_INDEX
    run([str(vpy), "-m", "pip", "install", *TORCH, "--index-url", index],
        f"Installing PyTorch ({'NVIDIA GPU / CUDA 12.8' if gpu else 'CPU'} build) - ~2.5 GB, takes a while")
    req = paths.REPO_DIR / "requirements-voice.txt"
    run([str(vpy), "-m", "pip", "install", *TORCH, "-r", str(req), "--extra-index-url", index],
        "Installing the voice model's packages")
    run([str(vpy), "-m", "pip", "install", CHATTERBOX, "--no-deps"], "Installing Chatterbox")

    probe = ("import json, torch, chatterbox.tts_turbo; ok = torch.cuda.is_available(); "
             "print(json.dumps({'torch': torch.__version__, 'cuda': ok, "
             "'gpu': torch.cuda.get_device_name(0) if ok else ''}))")
    r = subprocess.run([str(vpy), "-c", probe], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        say("FAIL", "The voice packages installed but don't import (details above).")
        return 1
    info = json.loads(r.stdout.strip().splitlines()[-1])
    say(" OK ", f"PyTorch {info['torch']}" + (f" on {info['gpu']}" if info["cuda"] else " (CPU)"))
    if gpu and not info["cuda"]:
        say("WARN", "An NVIDIA GPU is present but PyTorch can't use it - she'll talk, just slower.")

    # 3. model download + test line
    if not a.no_test:
        out = paths.voice_cache_dir() / "tts" / "_selftest.wav"
        say("....", "Downloading the voice model (~1.5 GB, one time) and saying a test line")
        t0 = time.time()
        # stderr stays on the console so the download progress is visible
        r = subprocess.run([str(vpy), "-m", "capricorn.tts.worker", "--reference", str(ref), "--selftest", str(out)],
                           cwd=str(paths.REPO_DIR), stdout=subprocess.PIPE, text=True, encoding="utf-8",
                           errors="replace")
        lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
        msgs = [json.loads(ln) for ln in lines]
        test = next((m for m in msgs if "selftest" in m), None)
        hello = next((m for m in msgs if "ready" in m), {})
        if not test or not test.get("selftest"):
            err = (test or {}).get("error") or hello.get("error") or "see the messages above"
            say("FAIL", f"Test line failed: {err}")
            return 1
        say(" OK ", f"Model loaded on {hello.get('gpu') or hello.get('device')} in {hello.get('load_s')}s; "
                    f"a {test['ms'] / 1000:.1f}s line took {test['took']}s to make "
                    f"(total {time.time() - t0:.0f}s incl. download)")
        if sys.platform == "win32" and not a.no_play:
            import winsound
            say("....", "Playing the test line...")
            winsound.PlaySound(str(out), winsound.SND_FILENAME)

    # 4. switch it on
    from capricorn.config import Settings
    s = Settings()
    s.set_and_save("voice.engine", "capri")
    s.set_and_save("voice.reference", ref.name)
    say(" OK ", "Capri's voice is ON (voice.engine = capri). Restart Capricorn to hear her.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
