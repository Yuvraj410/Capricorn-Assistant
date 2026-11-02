"""Spoken-form text for the voice model. TTS models read raw digits badly ("9:51" -> "nine thousand
fifty one"), so everything that isn't plain words is spelled out the way a person would say it:

    9:51 PM          -> nine fifty-one P M          November 1   -> November first
    2026             -> twenty twenty-six             $4.99        -> four dollars and ninety-nine cents
    45%              -> forty-five percent            3.5 GB       -> three point five gigabytes
    1,500            -> one thousand five hundred     2nd          -> second
    v1.2             -> version one point two         5-10         -> five to ten
    GPU / ngl / fr   -> G P U / not gonna lie / for real
The chat bubble keeps the original text; only what she *says* changes.
"""
from __future__ import annotations

import re

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
        "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SCALES = [(10 ** 12, "trillion"), (10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")]
ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
       "nine": "ninth", "twelve": "twelfth"}
MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|"
          "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
UNITS = {
    "gb": "gigabytes", "mb": "megabytes", "kb": "kilobytes", "tb": "terabytes", "gbps": "gigabits per second",
    "mbps": "megabits per second", "ghz": "gigahertz", "mhz": "megahertz", "hz": "hertz", "fps": "F P S",
    "ms": "milliseconds", "km": "kilometers", "kmh": "kilometers per hour", "mph": "miles per hour",
    "kg": "kilograms", "lbs": "pounds", "lb": "pounds", "cm": "centimeters", "mm": "millimeters",
    "°c": "degrees Celsius", "°f": "degrees Fahrenheit", "°": "degrees", "w": "watts", "v": "volts",
    "k": "thousand", "min": "minutes", "mins": "minutes", "hrs": "hours", "hr": "hours", "sec": "seconds",
    "secs": "seconds",
}
# Read as letters. Anything else in ALL CAPS is just emphasis and is read as a normal word.
ACRONYMS = {
    "AI", "PC", "GPU", "CPU", "SSD", "HDD", "USB", "HDMI", "VPN", "URL", "UI", "OS", "RTX", "GTX", "MSI",
    "NPC", "GG", "IRL", "OP", "AFK", "BRB", "DM", "DMs", "TV", "FPS", "RPG", "MMO", "DLC", "PS5", "XP",
    "HP", "API", "PDF", "ID", "IP", "FAQ", "LOL", "OMG", "CEO", "DIY", "EU", "UK", "US", "USA", "AV", "PS", "NPCs",
    "BD", "LED", "LCD", "RGB", "VR", "AR", "IT", "HR", "PR", "QA", "ETA", "SUV", "DJ", "MC", "UFO", "ATM",
}
WORDS_IN_CAPS = {"OK": "okay", "RAM": "ram", "ICE": "ice", "NASA": "NASA", "GIF": "gif", "JPEG": "jay-peg",
                 "PNG": "P N G", "WIFI": "wifi", "LMAO": "L-mao", "YOLO": "yolo", "GOAT": "goat"}
# internet / Gen Z shorthand said in full
SHORTHAND = {
    "fr": "for real", "frfr": "for real for real", "ngl": "not gonna lie", "tbh": "to be honest",
    "idk": "I don't know", "imo": "in my opinion", "imho": "in my humble opinion", "smh": "shaking my head",
    "btw": "by the way", "rn": "right now", "nvm": "never mind", "ty": "thank you", "thx": "thanks",
    "pls": "please", "plz": "please", "omw": "on my way", "istg": "I swear to god", "iykyk": "if you know you know",
    "fyi": "F Y I", "tho": "though", "w/": "with", "w/o": "without",
    "bc": "because", "b/c": "because", "cuz": "cuz", "ppl": "people", "gonna": "gonna", "lowkey": "low-key",
    "highkey": "high-key", "delulu": "deh-loo-loo", "bussin": "bussin'", "cheugy": "chew-ghee", "sus": "suss",
    "rizz": "rizz", "periodt": "periodt", "6-7": "six seven", "67": "six seven",
}


def words(n: int) -> str:
    if n < 0:
        return "minus " + words(-n)
    if n < 20:
        return ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return TENS[t] + (f"-{ONES[o]}" if o else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return f"{ONES[h]} hundred" + (f" {words(r)}" if r else "")
    for size, name in SCALES:
        if n >= size:
            q, r = divmod(n, size)
            return f"{words(q)} {name}" + (f" {words(r)}" if r else "")
    return str(n)


def ordinal(n: int) -> str:
    w = words(n)
    head, sep, last = w.rpartition("-") if "-" in w.split(" ")[-1] else w.rpartition(" ")
    last = last or w
    if last in ORD:
        last = ORD[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return f"{head}{sep}{last}" if head else last


def year(n: int) -> str:
    if 2000 <= n <= 2009:
        return words(n)
    if 1100 <= n <= 2099 and n % 100 != 0:
        hi, lo = divmod(n, 100)
        return f"{words(hi)} {'oh ' + words(lo) if lo < 10 else words(lo)}"
    if 1100 <= n <= 2099:
        return f"{words(n // 100)} hundred"
    return words(n)


def _time(m: re.Match) -> str:
    h, mi = int(m.group("h")), int(m.group("m"))
    ap = (m.group("ap") or "").lower().replace(".", "")
    if not ap and h > 12:                      # 24-hour clock -> spoken 12-hour
        ap, h = "pm", h - 12
    elif not ap and h == 0:
        ap, h = "am", 12
    hour = words(h)
    minute = "" if mi == 0 else (f" oh {words(mi)}" if mi < 10 else f" {words(mi)}")
    if not ap:
        return hour + (minute or " o'clock")
    return f"{hour}{minute} {'A M' if ap.startswith('a') else 'P M'}"


def _decimal(s: str) -> str:
    whole, _, frac = s.partition(".")
    out = words(int(whole.replace(",", "") or 0))
    if frac:
        out += " point " + " ".join(ONES[int(d)] for d in frac)
    return out


def _money(m: re.Match) -> str:
    amount = m.group("amt").replace(",", "")
    scale = (m.group("scale") or "").lower()
    whole, _, cents = amount.partition(".")
    if scale:
        return f"{_decimal(amount)} {dict(k='thousand', m='million', b='billion', bn='billion').get(scale, scale)} dollars"
    d = int(whole or 0)
    out = f"{words(d)} dollar{'s' if d != 1 else ''}"
    if cents and int(cents.ljust(2, '0')[:2]):
        c = int(cents.ljust(2, "0")[:2])
        out += f" and {words(c)} cent{'s' if c != 1 else ''}"
    return out


def _number(m: re.Match) -> str:
    s = m.group(0)
    digits = s.replace(",", "")
    if "." in digits:
        return _decimal(digits)
    if len(digits) > 1 and digits.startswith("0"):
        return " ".join(ONES[int(d)] for d in digits)        # 007, zip codes
    n = int(digits)
    if len(digits) >= 10 and "," not in s:
        return " ".join(ONES[int(d)] for d in digits)        # IDs, phone numbers
    if "," not in s and 1100 <= n <= 2099 and len(digits) == 4:
        return year(n)
    return words(n)


def normalize(text: str) -> str:
    t = text
    for k, v in (("6-7", "six seven"),):
        t = t.replace(k, v)
    t = re.sub(r"\b([248])K\b", lambda m: f"{words(int(m.group(1)))} K", t, flags=re.I)   # 4K
    # hardware model numbers: RTX 5070 -> R T X fifty seventy, 7950X3D -> seventy-nine fifty X 3 D
    t = re.sub(r"\b(\d{2})(\d{2})(X3D|XT|X|KF|K|F|Ti|HX|H|U)\b",
               lambda m: f"{words(int(m.group(1)))} {words(int(m.group(2))) if int(m.group(2)) else 'hundred'} "
                         f"{' '.join(m.group(3).replace('3', ' three ').split()) if m.group(3) != 'Ti' else 'tie'}", t)
    t = re.sub(r"\b(RTX|GTX|RX|GT|Ryzen\s?\d?|i[3579]-?)\s?(\d{2})(\d{2})\b",
               lambda m: f"{m.group(1)} {words(int(m.group(2)))} {words(int(m.group(3))) if int(m.group(3)) else 'hundred'}", t)
    # times: 9:51 PM, 21:30, 9:05am, 7 PM
    t = re.sub(r"\b(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)(?::\d\d)?\s*(?P<ap>[ap]\.?m)?(?![\w])", _time, t, flags=re.I)
    t = re.sub(r"\b(?P<h>1[0-2]|0?[1-9])\s*(?P<ap>[ap]\.?m)(?![\w])",
               lambda m: f"{words(int(m.group('h')))} {'A M' if m.group('ap')[0].lower() == 'a' else 'P M'}", t, flags=re.I)
    # dates: November 1 / Nov 1st / 1 November / 2026-11-01
    t = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: f"{MONTH_NAMES[int(m.group(2)) - 1]} "
               f"{ordinal(int(m.group(3)))}, {year(int(m.group(1)))}", t)
    t = re.sub(rf"\b({MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!:)",
               lambda m: f"{_month(m.group(1))} {ordinal(int(m.group(2)))}", t, flags=re.I)
    t = re.sub(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTHS})\b",
               lambda m: f"the {ordinal(int(m.group(1)))} of {_month(m.group(2))}", t, flags=re.I)
    t = re.sub(r"\b(the)\s+the\b", r"\1", t, flags=re.I)
    t = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: ordinal(int(m.group(1))), t, flags=re.I)
    # money, percent, versions, ranges, #1, x2
    t = re.sub(r"\$(?P<amt>\d[\d,]*(?:\.\d+)?)(?:\s?(?P<scale>k|m|bn|b)\b)?", _money, t, flags=re.I)
    t = re.sub(r"(\d[\d,]*(?:\.\d+)?)\s*%", lambda m: _decimal(m.group(1).replace(",", "")) + " percent", t)
    t = re.sub(r"\bv(\d+(?:\.\d+)+)\b", lambda m: "version " + " point ".join(words(int(p)) for p in m.group(1).split(".")), t, flags=re.I)
    t = re.sub(r"(?<![\w.])(\d+)\s*[-–]\s*(\d+)(?![\w.:])", lambda m: f"{m.group(1)} to {m.group(2)}", t)
    t = re.sub(r"#(\d+)", lambda m: "number " + m.group(1), t)
    t = re.sub(r"\bx(\d+)\b", lambda m: "times " + m.group(1), t)
    t = re.sub(r"\b(\d+)x\b", lambda m: m.group(1) + " times", t)
    t = re.sub(r"\b(\d+)([A-Z]{1,3})\b", lambda m: f"{m.group(1)} {' '.join(m.group(2))}", t)   # 275HX
    t = re.sub(r"(?<=\w )Ti\b", "tie", t)
    # number + unit: 3.5 GB, 144hz, 20°C, 4K
    unit_rx = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
    t = re.sub(rf"(\d[\d,]*(?:\.\d+)?)\s?({unit_rx})(?![a-z])",
               lambda m: f"{m.group(1)} {UNITS[m.group(2).lower()]}", t, flags=re.I)
    # remaining numbers
    t = re.sub(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])", _number, t)
    t = re.sub(r"(?<=[a-zA-Z])(\d+)\b", lambda m: " " + words(int(m.group(1))), t)   # PS5 -> PS five
    # shorthand / slang / acronyms
    t = re.sub(r"(?<![\w/])[A-Za-z][A-Za-z/]*(?![\w/])", _word, t)
    return re.sub(r"\s+", " ", t).strip()


MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"]


def _month(name: str) -> str:
    low = name.lower()[:3]
    return next((mn for mn in MONTH_NAMES if mn.lower().startswith(low)), name)


def _word(m: re.Match) -> str:
    w = m.group(0)
    low = w.lower()
    if len(w) >= 3 and w.endswith("s") and w[:-1].isupper() and w[:-1] in ACRONYMS:
        return " ".join(w[:-1]) + "s"            # DMs, NPCs, GPUs
    if low in SHORTHAND and (w.islower() or len(w) > 2 or low in {"fr", "rn", "ty"}):
        return SHORTHAND[low]
    if w.isupper() and len(w) >= 2:
        if w in WORDS_IN_CAPS:
            return WORDS_IN_CAPS[w]
        if w in ACRONYMS or w.rstrip("S") in ACRONYMS:
            core, plural = (w[:-1], "s") if w not in ACRONYMS and w.endswith("S") else (w, "")
            return " ".join(core) + plural
        return low                              # "NO WAY" is emphasis, not letters
    return w
