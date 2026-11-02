"""Cyberpunk chat theme (from the Capricorn Chat theme sheet)."""
from __future__ import annotations

import logging

from PyQt6.QtGui import QColor, QFont, QFontDatabase

from .. import paths

log = logging.getLogger(__name__)

TEXT = QColor("#F4F1FA")
SECONDARY = QColor("#B7A8C8")
PINK = QColor("#FF0060")
CYAN = QColor("#36DFFF")
GREEN = QColor("#00F45B")
BUBBLE = QColor("#171020")
BUBBLE_USER = QColor("#1E0A1C")
PURPLE = QColor("#7B3CFF")
BG = QColor("#0D0A14")

HEADING_FAMILY = "Rajdhani"
BODY_FAMILY = "Inter"
_FALLBACK_HEADING = "Bahnschrift"
_FALLBACK_BODY = "Segoe UI"
_loaded = {"heading": None, "body": None}


def load_fonts() -> None:
    for f in paths.FONTS_DIR.glob("*.ttf"):
        fid = QFontDatabase.addApplicationFont(str(f))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        for fam in fams:
            if fam.lower().startswith("rajdhani"):
                _loaded["heading"] = fam
            elif fam.lower().startswith("inter"):
                _loaded["body"] = fam
    log.info("fonts: %s", _loaded)


def heading_font(px: int = 16) -> QFont:
    f = QFont(_loaded["heading"] or _FALLBACK_HEADING)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight.DemiBold)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
    return f


def body_font(px: int = 15) -> QFont:
    f = QFont(_loaded["body"] or _FALLBACK_BODY)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight.Medium)
    return f


def rgba(c: QColor, a: int) -> QColor:
    c2 = QColor(c)
    c2.setAlpha(a)
    return c2


STYLESHEET = f"""
QWidget#ChatRoot {{ background: {BG.name()}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a2b4d; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background: {BUBBLE.name()}; color: {TEXT.name()}; border: 2px solid {CYAN.name()};
    padding: 9px 12px; font-size: 15px; selection-background-color: {PINK.name()};
}}
QLineEdit:focus {{ border-color: {PINK.name()}; }}
QPushButton {{
    background: {BUBBLE.name()}; color: {TEXT.name()}; border: 2px solid {PINK.name()};
    padding: 8px 16px; font-weight: 600; letter-spacing: 1px;
}}
QPushButton:hover {{ background: #2a1030; }}
QPushButton:pressed {{ background: {PINK.name()}; }}
QLabel#Title {{ color: {PINK.name()}; }}
QLabel#SubTitle {{ color: {CYAN.name()}; }}
QLabel#Status {{ color: {SECONDARY.name()}; font-size: 12px; }}
QMenu {{ background: {BUBBLE.name()}; color: {TEXT.name()}; border: 1px solid {CYAN.name()}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; }}
QMenu::item:selected {{ background: #2a1030; color: {CYAN.name()}; }}
QMenu::item:disabled {{ color: {SECONDARY.name()}; }}
QMenu::separator {{ height: 1px; background: #3a2b4d; margin: 4px 8px; }}
QMenu::indicator {{ width: 12px; height: 12px; }}
"""
