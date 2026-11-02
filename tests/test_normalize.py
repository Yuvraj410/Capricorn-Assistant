"""What Capri's voice actually reads (the bubble keeps the original text)."""
import pytest

from capricorn.tts.normalize import normalize, ordinal, words, year
from capricorn.tts import textprep

CASES = [
    ("9:51 PM. Sunday, November 1.", "nine fifty-one P M. Sunday, November first."),
    ("It's 21:30.", "It's nine thirty P M."),
    ("Meet at 7pm", "Meet at seven P M"),
    ("9:05 am", "nine oh five A M"),
    ("It's 12:00 PM", "It's twelve P M"),
    ("2026 was wild", "twenty twenty-six was wild"),
    ("$4.99 or $1,250", "four dollars and ninety-nine cents or one thousand two hundred fifty dollars"),
    ("45% done", "forty-five percent done"),
    ("3.5 GB left", "three point five gigabytes left"),
    ("the 2nd one", "the second one"),
    ("v1.2 is out", "version one point two is out"),
    ("5-10 minutes", "five to ten minutes"),
    ("GPU at 87%", "G P U at eighty-seven percent"),
    ("ngl that's fr bussin", "not gonna lie that's for real bussin'"),
    ("NO WAY, choom. OK fine.", "no way, choom. okay fine."),
    ("PS5 and RTX 5070", "P S five and R T X fifty seventy"),
    ("1,500 eddies", "one thousand five hundred eddies"),
    ("Nov 22nd", "November twenty-second"),
    ("on the 3rd of March", "on the third of March"),
    ("4K at 120 fps", "four K at one hundred twenty F P S"),
    ("#1 priority", "number one priority"),
    ("3x faster", "three times faster"),
    ("it's 6-7", "it's six seven"),
]


@pytest.mark.parametrize("src,said", CASES)
def test_normalize(src, said):
    assert normalize(src) == said


def test_number_words():
    assert words(0) == "zero" and words(115) == "one hundred fifteen" and words(2_000_001) == "two million one"
    assert ordinal(1) == "first" and ordinal(22) == "twenty-second" and ordinal(30) == "thirtieth" and ordinal(12) == "twelfth"
    assert year(2026) == "twenty twenty-six" and year(2005) == "two thousand five" and year(1907) == "nineteen oh seven"


def test_time_reply_end_to_end():
    parts = textprep.for_speech("9:51 PM. Sunday, November 1.", "neutral")
    assert " ".join(parts) == "nine fifty-one P M. Sunday, November first."
