import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from split_voice_lines import align

def test_align_handles_merged_lines_and_internal_pauses():
    lines = ["Ha! Okay, that was good.", "Whoa, seriously?", "Ugh. Fine.", "Later, choom."]
    # recogniser output with timings; whisper heard "chum" for "choom"
    rec = "ha okay that was good whoa seriously ugh fine later chum".split()
    words = [(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate(rec)]
    spans = align(lines, words)
    assert spans[0] == (0.0, 2.4)          # ha .. good
    assert spans[1] == (2.5, 3.4)          # whoa seriously
    assert spans[2] == (3.5, 4.4)          # ugh fine
    assert spans[3] == (4.5, 4.9)          # "later" matched, "chum" not -> still located
