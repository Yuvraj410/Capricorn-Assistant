"""Split recorded "line packs" into one clip per line, using Whisper WORD timestamps, then verify.

A line pack is an audio file (mp3/wav) with a matching .txt that has one line per row, e.g.
    lines-1.mp3 + lines-1.txt
Each line is cut from its first to its last word, checked by transcribing the clip again,
and added to capricorn-data\\voice_cache\\index.json so Capri can play it instantly.

Usage (from the repo folder):
    capricorn-data\\python\\Scripts\\python tools\\split_voice_lines.py "C:\\path\\to\\reference-voices"
    capricorn-data\\python\\Scripts\\python tools\\split_voice_lines.py "C:\\path\\to\\reference-voices" --transcribe-missing
--transcribe-missing also writes a .txt for any long clip that has none.
Your recordings are only read, never modified.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capricorn import paths  # noqa: E402

OUT_RATE = 44100
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "line"


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm_words(a), norm_words(b)).ratio()


def align(lines: list[str], words: list[tuple[str, float, float]]) -> list[tuple[float, float] | None]:
    """Map each expected line to (start, end) seconds using the recognised word sequence."""
    rec = [w for w, _, _ in words]
    exp_flat, owner = [], []
    for i, line in enumerate(lines):
        for w in norm_words(line):
            exp_flat.append(w)
            owner.append(i)
    sm = difflib.SequenceMatcher(None, exp_flat, rec, autojunk=False)
    spans: list[list[float]] = [[] for _ in lines]
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            li = owner[a + k]
            _, st, en = words[b + k]
            spans[li] += [st, en]
    out = []
    for s in spans:
        out.append((min(s), max(s)) if s else None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--transcribe-missing", action="store_true")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--min-sim", type=float, default=0.8, help="verification threshold (0-1)")
    args = ap.parse_args()

    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    model = WhisperModel(args.model, device="cpu", compute_type="int8",
                         download_root=str(paths.models_dir() / "whisper"))
    out_dir = paths.voice_cache_dir()
    index_path = out_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    known = {i["file"] for i in index}

    audio_files = sorted(p for p in args.folder.iterdir() if p.suffix.lower() in AUDIO_EXT)
    if args.transcribe_missing:
        for p in audio_files:
            txt = p.with_suffix(".txt")
            if not txt.exists():
                segs, _ = model.transcribe(str(p), language="en", beam_size=5)
                text = " ".join(s.text.strip() for s in segs).strip()
                txt.write_text(text + "\n", encoding="utf-8")
                print(f"[ OK ] transcribed {p.name}:\n       {text}")

    packs = [p for p in audio_files if p.stem.lower().startswith("lines") and p.with_suffix(".txt").exists()]
    if not packs:
        print("No line packs found (expected lines-*.mp3 with lines-*.txt next to them).")
        return 0
    ok_count = bad_count = 0
    for pack in packs:
        lines = [l.strip() for l in pack.with_suffix(".txt").read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"\n== {pack.name}: {len(lines)} lines")
        segs, _ = model.transcribe(str(pack), language="en", beam_size=5, word_timestamps=True,
                                   condition_on_previous_text=False)
        words = []
        for s in segs:
            for w in s.words or []:
                for t in norm_words(w.word):
                    words.append((t, float(w.start), float(w.end)))
        spans = align(lines, words)
        audio = decode_audio(str(pack), sampling_rate=OUT_RATE)
        for i, (line, span) in enumerate(zip(lines, spans)):
            name = f"{pack.stem}-{i + 1:02d}-{slug(line)}.wav"
            if span is None:
                print(f"  [FAIL] {line!r}: not found in the recording")
                bad_count += 1
                continue
            st = max(0.0, span[0] - 0.08)
            en = min(len(audio) / OUT_RATE, span[1] + 0.15)
            clip = audio[int(st * OUT_RATE): int(en * OUT_RATE)].copy()
            fade = min(len(clip) // 4, int(0.01 * OUT_RATE))
            if fade:
                clip[:fade] *= np.linspace(0, 1, fade)
                clip[-fade:] *= np.linspace(1, 0, fade)
            write_wav(out_dir / name, clip, OUT_RATE)
            # verify by transcribing the clip itself
            vsegs, _ = model.transcribe(clip if OUT_RATE == 16000 else decode_audio(str(out_dir / name)),
                                        language="en", beam_size=5)
            heard = " ".join(s.text.strip() for s in vsegs)
            sim = similarity(line, heard)
            if sim >= args.min_sim:
                ok_count += 1
                print(f"  [ OK ] {en - st:4.1f}s  {line}")
                if name not in known:
                    index.append({"text": line, "file": name})
                    known.add(name)
            else:
                bad_count += 1
                print(f"  [FAIL] {line!r} -> heard {heard!r} (match {sim:.0%}) - not added")
                (out_dir / name).unlink(missing_ok=True)
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{ok_count} clips verified and added, {bad_count} failed. Index: {index_path}")
    return 0 if bad_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
