"""Settings screen in the Capricorn chat style: every setting from settings.yaml, grouped by section,
with its explanation, a search box, Save / Save & restart, and a voice test box."""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import yaml
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QScrollArea, QSlider,
                             QSpinBox, QVBoxLayout, QWidget)

from ..config import Settings
from . import theme
from .settings_schema import SECTION_TITLES, Field, load_fields

log = logging.getLogger(__name__)

EXTRA_CSS = f"""
QWidget#SettingsRoot {{ background: {theme.BG.name()}; }}
QListWidget {{ background: {theme.BUBBLE.name()}; color: {theme.TEXT.name()}; border: 2px solid {theme.CYAN.name()};
    font-size: 14px; padding: 6px; outline: none; }}
QListWidget::item {{ padding: 9px 10px; }}
QListWidget::item:selected {{ background: #2a1030; color: {theme.CYAN.name()}; border-left: 3px solid {theme.PINK.name()}; }}
QFrame#Row {{ background: {theme.BUBBLE.name()}; border: 1px solid #2c2140; }}
QFrame#Row:hover {{ border-color: {theme.CYAN.name()}; }}
QLabel#Key {{ color: {theme.TEXT.name()}; font-size: 15px; font-weight: 700; }}
QLabel#Help {{ color: {theme.SECONDARY.name()}; font-size: 12px; }}
QLabel#Restart {{ color: {theme.PINK.name()}; font-size: 11px; font-weight: 700; }}
QLabel#Section {{ color: {theme.CYAN.name()}; }}
QLabel#Level {{ color: {theme.GREEN.name()}; font-size: 13px; font-weight: 700; min-width: 120px; }}
QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{ background: {theme.BG.name()}; color: {theme.TEXT.name()};
    border: 2px solid {theme.CYAN.name()}; padding: 5px 8px; font-size: 14px; min-width: 150px; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {theme.PINK.name()}; }}
QComboBox QAbstractItemView {{ background: {theme.BUBBLE.name()}; color: {theme.TEXT.name()};
    selection-background-color: #2a1030; border: 1px solid {theme.CYAN.name()}; }}
QCheckBox {{ color: {theme.TEXT.name()}; font-size: 14px; spacing: 10px; }}
QCheckBox::indicator {{ width: 44px; height: 22px; border: 2px solid {theme.SECONDARY.name()}; background: {theme.BG.name()}; }}
QCheckBox::indicator:checked {{ border-color: {theme.GREEN.name()}; background: #0b3d22; }}
QSlider::groove:horizontal {{ height: 6px; background: #2c2140; }}
QSlider::handle:horizontal {{ background: {theme.PINK.name()}; width: 16px; margin: -6px 0; }}
QSlider::sub-page:horizontal {{ background: {theme.CYAN.name()}; }}
QPushButton#Primary {{ border-color: {theme.GREEN.name()}; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 18px; background: #2c2140; border: none; }}
QAbstractSpinBox::up-arrow {{ width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent;
    border-bottom: 6px solid {theme.CYAN.name()}; }}
QAbstractSpinBox::down-arrow {{ width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent;
    border-top: 6px solid {theme.CYAN.name()}; }}
"""


class FieldEditor(QWidget):
    """One widget for one setting; .value() returns the parsed value."""
    changed = pyqtSignal()

    def __init__(self, f: Field, current: Any, extra_choices: Optional[list[str]] = None) -> None:
        super().__init__()
        self.f = f
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        spec, d = f.spec, f.default
        self.kind = "text"
        if "levels" in spec:
            self.kind = "level"
            self.w = QSlider(Qt.Orientation.Horizontal)
            self.w.setRange(0, len(spec["levels"]) - 1)
            self.w.setValue(int(current if current is not None else d))
            self.w.setFixedWidth(220)
            self.lvl = QLabel(spec["levels"][self.w.value()])
            self.lvl.setObjectName("Level")
            self.w.valueChanged.connect(lambda v: (self.lvl.setText(spec["levels"][v]), self.changed.emit()))
            lay.addWidget(self.w)
            lay.addWidget(self.lvl)
        elif "choices" in spec or extra_choices:
            self.kind = "choice"
            self.w = QComboBox()
            choices = list(spec.get("choices") or []) + [c for c in (extra_choices or []) if c not in spec.get("choices", [])]
            if current is not None and str(current) not in choices:
                choices.insert(0, str(current))
            self.w.addItems(choices)
            self.w.setEditable(bool(extra_choices))
            self.w.setCurrentText(str(current if current is not None else d))
            self.w.currentTextChanged.connect(lambda *_: self.changed.emit())
            lay.addWidget(self.w)
        elif isinstance(d, bool):
            self.kind = "bool"
            self.w = QCheckBox("On" if current else "Off")
            self.w.setChecked(bool(current))
            self.w.toggled.connect(lambda on: (self.w.setText("On" if on else "Off"), self.changed.emit()))
            lay.addWidget(self.w)
        elif isinstance(d, int) and not isinstance(d, bool) and not isinstance(current, float):
            self.kind = "int"
            lo, hi, step = spec.get("range", (-100000, 100000, 1))
            self.w = QSpinBox()
            self.w.setRange(int(lo), int(hi))
            self.w.setSingleStep(int(step))
            self.w.setValue(int(current if current is not None else d))
            self.w.valueChanged.connect(lambda *_: self.changed.emit())
            lay.addWidget(self.w)
        elif isinstance(d, (int, float)):
            self.kind = "float"
            lo, hi, step = spec.get("range", (-100000.0, 100000.0, 0.1))
            self.w = QDoubleSpinBox()
            self.w.setDecimals(2)
            self.w.setRange(float(lo), float(hi))
            self.w.setSingleStep(float(step))
            self.w.setValue(float(current if current is not None else d))
            self.w.valueChanged.connect(lambda *_: self.changed.emit())
            lay.addWidget(self.w)
        elif isinstance(d, dict):
            self.kind = "dict"
            self.w = QPlainTextEdit()
            self.w.setPlaceholderText("one per line:  name: value")
            cur = current or {}
            self.w.setPlainText("\n".join(f"{k}: {v}" for k, v in cur.items()))
            self.w.setFixedHeight(90)
            self.w.textChanged.connect(self.changed.emit)
            lay.addWidget(self.w)
        elif isinstance(d, list):
            self.kind = "list"
            self.w = QLineEdit(", ".join(str(x) for x in (current or [])))
            self.w.setPlaceholderText("comma separated")
            self.w.textChanged.connect(lambda *_: self.changed.emit())
            lay.addWidget(self.w)
        else:
            self.kind = "text"
            self.w = QLineEdit("" if current is None else str(current))
            self.w.setPlaceholderText("empty = default / automatic" if d is None else "")
            self.w.textChanged.connect(lambda *_: self.changed.emit())
            lay.addWidget(self.w)
        lay.addStretch(1) if self.kind in {"level", "bool", "int", "float", "choice"} else None

    def value(self) -> Any:
        k, w = self.kind, self.w
        if k == "level":
            return w.value()
        if k == "choice":
            return w.currentText().strip()
        if k == "bool":
            return w.isChecked()
        if k == "int":
            return w.value()
        if k == "float":
            return round(w.value(), 3)
        if k == "list":
            return [x.strip() for x in w.text().split(",") if x.strip()]
        if k == "dict":
            out = {}
            for line in w.toPlainText().splitlines():
                if ":" in line:
                    a, _, b = line.partition(":")
                    if a.strip():
                        out[a.strip()] = _scalar(b.strip())
            return out
        txt = w.text().strip()
        return None if txt == "" and self.f.default is None else _scalar(txt) if self.f.default is None else txt


def _scalar(s: str) -> Any:
    try:
        v = yaml.safe_load(s)
        return v if isinstance(v, (int, float, bool, list, type(None))) else s
    except yaml.YAMLError:
        return s


class SettingsWindow(QWidget):
    saved = pyqtSignal(dict, bool)          # changed values, restart needed

    def __init__(self, settings: Settings, speak: Optional[Callable[[str], None]] = None,
                 restart: Optional[Callable[[], None]] = None, models: Optional[Callable[[], list[str]]] = None) -> None:
        super().__init__(None)
        self.s = settings
        self.speak, self.restart_fn, self.models_fn = speak, restart, models
        self.setObjectName("SettingsRoot")
        self.setWindowTitle("Capricorn - Settings")
        self.setMinimumSize(900, 640)
        self.resize(1100, 760)
        self.setStyleSheet(theme.STYLESHEET + EXTRA_CSS)
        self.editors: dict[str, FieldEditor] = {}
        self.rows: dict[str, QFrame] = {}
        self._build()

    # -- layout ------------------------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(12)
        head = QHBoxLayout()
        for text, name in (("CAPRICORN", "Title"), ("SETTINGS", "SubTitle")):
            lab = QLabel(text)
            lab.setObjectName(name)
            lab.setFont(theme.heading_font(30))
            head.addWidget(lab)
        st = QLabel("///")
        st.setStyleSheet(f"color: {theme.PURPLE.name()};")
        st.setFont(theme.heading_font(30))
        head.addWidget(st)
        head.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search settings...")
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self._filter)
        head.addWidget(self.search)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.nav = QListWidget()
        self.nav.setFixedWidth(230)
        self.nav.setFont(theme.heading_font(16))
        body.addWidget(self.nav)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        inner = QWidget()
        self.form = QVBoxLayout(inner)
        self.form.setContentsMargins(0, 0, 10, 0)
        self.form.setSpacing(8)
        self.scroll.setWidget(inner)
        body.addWidget(self.scroll, 1)
        root.addLayout(body, 1)

        self.headers: dict[str, QLabel] = {}
        fields = load_fields()
        models = []
        if self.models_fn:
            try:
                models = self.models_fn()
            except Exception:
                models = []
        for sec in dict.fromkeys(f.section for f in fields):
            title = SECTION_TITLES.get(sec, sec.capitalize())
            QListWidgetItem(title, self.nav).setData(Qt.ItemDataRole.UserRole, sec)
            hl = QLabel(title.upper())
            hl.setObjectName("Section")
            hl.setFont(theme.heading_font(22))
            self.headers[sec] = hl
            self.form.addSpacing(6)
            self.form.addWidget(hl)
            for f in (x for x in fields if x.section == sec):
                extra = models if f.key == "brain.model" else None
                self._add_row(f, extra)
            if sec == "voice" and self.speak:
                self.form.addWidget(self._voice_test_row())
        self.form.addStretch(1)
        self.nav.currentItemChanged.connect(self._jump)

        foot = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("Status")
        foot.addWidget(self.status, 1)
        reset = QPushButton("RESET SECTION")
        reset.clicked.connect(self._reset_section)
        foot.addWidget(reset)
        save = QPushButton("SAVE")
        save.setObjectName("Primary")
        save.clicked.connect(lambda: self._save(restart=False))
        foot.addWidget(save)
        if self.restart_fn:
            sr = QPushButton("SAVE && RESTART CAPRI")
            sr.clicked.connect(lambda: self._save(restart=True))
            foot.addWidget(sr)
        root.addLayout(foot)

    def _add_row(self, f: Field, extra_choices) -> None:
        row = QFrame()
        row.setObjectName("Row")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(2)
        k = QLabel(f.label)
        k.setObjectName("Key")
        left.addWidget(k)
        if f.help:
            h = QLabel(f.help)
            h.setObjectName("Help")
            h.setWordWrap(True)
            left.addWidget(h)
        note = "   ·   needs restart" if f.needs_restart else ("   ·   reloads in a few seconds" if f.reloads else "")
        tag = QLabel(f"{f.key}{note}")
        tag.setObjectName("Restart" if f.needs_restart else "Help")
        left.addWidget(tag)
        lay.addLayout(left, 3)
        ed = FieldEditor(f, self.s.get(f.key, f.default), extra_choices)
        ed.changed.connect(self._dirty)
        lay.addWidget(ed, 2)
        self.editors[f.key] = ed
        self.rows[f.key] = row
        row.setProperty("search", f"{f.key} {f.label} {f.help}".lower())
        self.form.addWidget(row)

    def _voice_test_row(self) -> QFrame:
        row = QFrame()
        row.setObjectName("Row")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(14, 10, 14, 10)
        lab = QLabel("Test her voice")
        lab.setObjectName("Key")
        lay.addWidget(lab)
        self.test_line = QLineEdit("Preem choice, choomba. It's 9:51 PM, no cap.")
        lay.addWidget(self.test_line, 1)
        b = QPushButton("SPEAK")
        b.clicked.connect(lambda: self.speak(self.test_line.text()))
        lay.addWidget(b)
        row.setProperty("search", "test voice speak pronounce")
        self.rows["_voice_test"] = row
        return row

    # -- behaviour ---------------------------------------------------------------------------------
    def _jump(self, item, _prev=None) -> None:
        if item is None:
            return
        hl = self.headers.get(item.data(Qt.ItemDataRole.UserRole))
        if hl:
            self.scroll.verticalScrollBar().setValue(hl.y() - 4)

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for key, row in self.rows.items():
            row.setVisible(not t or t in (row.property("search") or ""))
        for sec, hl in self.headers.items():
            hl.setVisible(not t or any(r.isVisible() for k, r in self.rows.items() if k.startswith(sec + ".")))

    def _dirty(self) -> None:
        n = len(self.changes())
        self.status.setText(f"{n} unsaved change{'s' if n != 1 else ''}" if n else "")

    def changes(self) -> dict[str, Any]:
        out = {}
        for key, ed in self.editors.items():
            try:
                v = ed.value()
            except Exception:
                continue
            cur = self.s.get(key, ed.f.default)
            if v != cur and not (v in (None, "", [], {}) and cur in (None, "", [], {})):
                out[key] = v
        return out

    def _reset_section(self) -> None:
        item = self.nav.currentItem()
        if item is None:
            self.status.setText("Pick a section on the left first.")
            return
        sec = item.data(Qt.ItemDataRole.UserRole)
        for key, ed in list(self.editors.items()):
            if key.startswith(sec + "."):
                row = self.rows[key]
                lay = row.layout()
                lay.removeWidget(ed)
                ed.deleteLater()
                ne = FieldEditor(ed.f, ed.f.default, None)
                ne.changed.connect(self._dirty)
                lay.addWidget(ne, 2)
                self.editors[key] = ne
        self._dirty()
        self.status.setText(f"{SECTION_TITLES.get(sec, sec)}: back to defaults - press Save to keep.")

    def _save(self, restart: bool) -> None:
        ch = self.changes()
        if not ch and not restart:
            self.status.setText("Nothing changed.")
            return
        if ch:
            self.s.save_many(ch)
        needs = any(self.editors[k].f.needs_restart for k in ch)
        log.info("settings saved: %s", ch)
        self.saved.emit(ch, needs)
        if restart and self.restart_fn:
            self.status.setText("Saved. Restarting Capri...")
            self.restart_fn()
        elif needs:
            self.status.setText("Saved. Some changes apply after a restart (Save & restart).")
        elif any(self.editors[k].f.reloads for k in ch):
            self.status.setText("Saved - applied. The voice / speech model is reloading in the background.")
        else:
            self.status.setText("Saved - applied instantly.")

    def open(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
