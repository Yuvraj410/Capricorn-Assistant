"""Chat panel: the full conversation in the cyberpunk theme, plus a box to type commands."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

from .. import paths
from . import theme
from .bubble import Bubble


class Avatar(QLabel):
    """Square cyan-framed avatar like the theme sheet."""

    def __init__(self, size: int = 58) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        pm = QPixmap(str(paths.CHARACTER_DIR / "smile.png"))
        if not pm.isNull():
            # crop to the face (the art is 512x512 with the head in the upper-middle)
            from PyQt6.QtCore import QRect
            w, h = pm.width(), pm.height()
            pm = pm.copy(QRect(int(w * 0.17), int(h * 0.04), int(w * 0.66), int(h * 0.66)))
            inner = size - 8
            pm = pm.scaled(inner * 2, inner * 2, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(2.0)
        self._pm = pm

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        c = 7
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QPainterPath, QPolygonF
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(r.left(), r.top()), QPointF(r.right() - c, r.top()),
                                   QPointF(r.right(), r.top() + c), QPointF(r.right(), r.bottom()),
                                   QPointF(r.left() + c, r.bottom()), QPointF(r.left(), r.bottom() - c)]))
        path.closeSubpath()
        p.fillPath(path, theme.BUBBLE)
        p.setClipPath(path)
        if not self._pm.isNull():
            p.drawPixmap(r.adjusted(2, 2, -2, -2), self._pm)
        p.setClipping(False)
        p.setPen(QPen(theme.CYAN, 2))
        p.drawPath(path)
        p.end()


class ChatWindow(QWidget):
    submitted = pyqtSignal(str)
    answered = pyqtSignal(bool)
    settings_requested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setObjectName("ChatRoot")
        self.setWindowTitle("Capricorn - Chat")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumSize(460, 560)
        self.resize(520, 680)
        self.setStyleSheet(theme.STYLESHEET)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("CAPRICORN")
        title.setObjectName("Title")
        title.setFont(theme.heading_font(30))
        sub = QLabel("CHAT")
        sub.setObjectName("SubTitle")
        sub.setFont(theme.heading_font(30))
        stripes = QLabel("///")
        stripes.setStyleSheet(f"color: {theme.PURPLE.name()};")
        stripes.setFont(theme.heading_font(30))
        head.addWidget(title)
        head.addWidget(sub)
        head.addWidget(stripes)
        head.addStretch(1)
        gear = QPushButton("SETTINGS")
        gear.setFont(theme.heading_font(15))
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.clicked.connect(self.settings_requested.emit)
        head.addWidget(gear)
        root.addLayout(head)
        self.status = QLabel("")
        self.status.setObjectName("Status")
        root.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.feed = QWidget()
        self.feed_lay = QVBoxLayout(self.feed)
        self.feed_lay.setContentsMargins(0, 6, 6, 6)
        self.feed_lay.setSpacing(14)
        self.feed_lay.addStretch(1)
        self.scroll.setWidget(self.feed)
        root.addWidget(self.scroll, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a command... (e.g. open youtube, play lofi, what's playing)")
        self.input.setFont(theme.body_font(15))
        self.input.returnPressed.connect(self._send)
        send = QPushButton("SEND")
        send.setFont(theme.heading_font(16))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send)
        row.addWidget(self.input, 1)
        row.addWidget(send)
        root.addLayout(row)
        self._pending_bubble: Bubble | None = None

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)

    def _bubble_width(self) -> int:
        return max(220, self.width() - 170)

    def add_user(self, text: str) -> None:
        b = Bubble("user", tail="none", max_text_width=self._bubble_width(), font_px=15, glow=False)
        b.set_text(text, typewriter=False)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(b)
        self._add_row(row)

    def add_capri(self, text: str, ask: bool = False) -> Bubble:
        b = Bubble("capri", tail="left", max_text_width=self._bubble_width(), font_px=15, glow=False)
        b.set_text(text, typewriter=False, ask=ask)
        if ask:
            b.answered.connect(self._on_answer)
            self._pending_bubble = b
        row = QHBoxLayout()
        av = Avatar()
        row.addWidget(av, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        row.addStretch(1)
        self._add_row(row)
        return b

    def close_question(self) -> None:
        if self._pending_bubble is not None:
            self._pending_bubble.buttons.hide()
            self._pending_bubble._relayout()
            self._pending_bubble = None

    def _on_answer(self, yes: bool) -> None:
        self.close_question()
        self.answered.emit(yes)

    def _add_row(self, row: QHBoxLayout) -> None:
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.feed_lay.insertWidget(self.feed_lay.count() - 1, w)
        QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def open(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
