"""`python -m capricorn --check` - verifies the install and prints what's missing."""
from __future__ import annotations

import importlib
import sys

from . import paths
from .config import Settings

OK, WARN, BAD = "[ OK ]", "[WARN]", "[FAIL]"


def run_checks() -> int:
    s = Settings()
    fails = 0
    print(f"Capricorn check - Python {sys.version.split()[0]} - user data: {paths.user_dir()}\n")

    for mod, why in [("PyQt6", "UI"), ("yaml", "config"), ("requests", "Ollama"), ("numpy", "audio"),
                     ("sounddevice", "microphone"), ("vosk", "wake word"), ("faster_whisper", "speech-to-text"),
                     ("rapidfuzz", "fuzzy matching")]:
        try:
            importlib.import_module(mod)
            print(f"{OK} {mod:<15} ({why})")
        except Exception as e:
            fails += 1
            print(f"{BAD} {mod:<15} ({why}) - {e}")
    for mod, why in [("winrt.windows.media.control", "'what's playing'"), ("win32com.client", "Windows voice")]:
        try:
            importlib.import_module(mod)
            print(f"{OK} {mod:<15} ({why})")
        except Exception:
            print(f"{WARN} {mod:<15} ({why}) - optional, not installed")

    from .audio.listener import find_vosk_model
    vm = find_vosk_model()
    print(f"{OK if vm else BAD} wake-word model: {vm or 'missing - run Setup.exe'}")
    fails += 0 if vm else 1

    try:
        import sounddevice as sd
        dev = sd.query_devices(kind="input")
        print(f"{OK} microphone: {dev['name']}")
    except Exception as e:
        fails += 1
        print(f"{BAD} microphone: {e}")

    from .brain.llm import LLM
    ok, msg = LLM(s).status()
    print(f"{OK if ok else WARN} brain ({s.get('brain.model')}): {msg}")

    try:
        from .audio.stt import STT
        stt = STT(s)
        stt.preload()
        print(f"{OK} speech-to-text: whisper {s.get('stt.model')} on {stt._device}")
    except Exception as e:
        fails += 1
        print(f"{BAD} speech-to-text: {e}")

    from .tts.engine import TTS
    from .tts.capri_voice import CapriVoice
    tts = TTS(s)
    eng = tts.engine()
    if CapriVoice.installed():
        ref = tts.reference()
        print(f"{OK if ref.exists() else WARN} voice: engine={eng}, reference "
              f"{ref.name if ref.exists() else 'missing: ' + str(ref)} (test: commands\\test-voice.bat)")
    else:
        print(f"{WARN} voice: engine={eng} - Capri's own voice not installed (commands\\install-capri-voice.bat)")
    print("\nAll good - start Capricorn with Capricorn.bat" if not fails else f"\n{fails} problem(s) - see above")
    return 1 if fails else 0
