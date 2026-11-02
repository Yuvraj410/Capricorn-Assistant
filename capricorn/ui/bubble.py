"""The cyberpunk speech bubble: chamfered neon frame, accent tabs, tail, typewriter text."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from . import theme

PAD_X, PAD_Y = 22, 16
CHAMFER = 14
TAIL_W, TAIL_H = 18, 22
TAB_H = 9


class Bubble(QWidget):
    """side='capri' -> cyan frame; side='user' -> pink frame.
    tail='left' | 'right' | 'none' - which side the tail points to."""

    finished = pyqtSignal()        # typewriter done
    answered = pyqtSignal(bool)    # confirm buttons

    def __init__(self, side: str = "capri", tail: str = "left", max_text_width: int = 320,
                 font_px: int = 16, glow: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.side, self.tail = side, tail
        self.max_text_width = max_text_width
        self._font = theme.body_font(font_px)
        self._cap_font = theme.body_font(max(11, font_px - 4))
        self.full_text = ""
        self.caption = ""
        self.shown_chars = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._cps = 45
        self._dots = 0
        self._dots_timer = QTimer(self)
        self._dots_timer.timeout.connect(self._tick_dots)
        self.thinking = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if glow:
            fx = QGraphicsDropShadowEffect(self)
            fx.setBlurRadius(22)
            fx.setOffset(0, 0)
            fx.setColor(theme.rgba(self.color, 150))
            self.setGraphicsEffect(fx)
        # confirm buttons (hidden unless asking)
        self.buttons = QWidget(self)
        lay = QHBoxLayout(self.buttons)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.yes_btn, self.no_btn = QPushButton("YES"), QPushButton("NO")
        for b, val in ((self.yes_btn, True), (self.no_btn, False)):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(theme.heading_font(15))
            b.clicked.connect(lambda _=False, v=val: self.answered.emit(v))
            lay.addWidget(b)
        self.yes_btn.setStyleSheet(f"border-color: {theme.GREEN.name()};")
        self.buttons.hide()
        self._relayout()

    @property
    def color(self):
        return theme.CYAN if self.side == "capri" else theme.PINK

    # -- content ---------------------------------------------------------------------------
    def set_text(self, text: str, caption: str = "", typewriter: bool = True, cps: int = 45,
                 ask: bool = False) -> None:
        self.thinking = False
        self._dots_timer.stop()
        self.full_text = text
        self.caption = caption
        self._cps = max(5, cps)
        self.buttons.setVisible(ask)
        if typewriter and text:
            self.shown_chars = 0
            self._timer.start(int(1000 / self._cps))
        else:
            self.shown_chars = len(text)
            self._timer.stop()
        self._relayout()
        self.update()
        if not typewriter:
            self.finished.emit()

    def set_thinking(self, caption: str = "") -> None:
        """Animated '...' bubble."""
        self._timer.stop()
        self.buttons.hide()
        self.thinking = True
        self.full_text = "•••"
        self.shown_chars = 3
        self.caption = caption
        self._dots = 0
        self._dots_timer.start(330)
        self._relayout()
        self.update()

    def set_caption(self, caption: str) -> None:
        """Change only the small line under the text (e.g. 'listening for your reply...')."""
        if caption == self.caption:
            return
        self.caption = caption
        self._relayout()
        self.update()

    def typing_duration_ms(self) -> int:
        return int(1000 * len(self.full_text) / self._cps)

    def _tick(self) -> None:
        self.shown_chars += 1
        if self.shown_chars >= len(self.full_text):
            self.shown_chars = len(self.full_text)
            self._timer.stop()
            self.finished.emit()
        self.update()

    def _tick_dots(self) -> None:
        self._dots = (self._dots + 1) % 4
        self.update()

    # -- geometry ------------------------------------------------------------------------------
    def _text_rect_size(self) -> tuple[int, int, int]:
        fm = QFontMetrics(self._font)
        flags = int(Qt.TextFlag.TextWordWrap)
        text = self.full_text or " "
        br = fm.boundingRect(0, 0, self.max_text_width, 10000, flags, text)
        w = max(br.width(), 40)
        h = br.height()
        ch = 0
        if self.caption:
            cfm = QFontMetrics(self._cap_font)
            cbr = cfm.boundingRect(0, 0, self.max_text_width, 1000, flags, self.caption)
            w = max(w, min(cbr.width(), self.max_text_width))
            ch = cbr.height() + 6
        return w, h, ch

    def _relayout(self) -> None:
        w, h, ch = self._text_rect_size()
        btn_h = 0
        if self.buttons.isVisible() or self.buttons.isVisibleTo(self):
            self.buttons.adjustSize()
            btn_h = self.buttons.sizeHint().height() + 12
            w = max(w, self.buttons.sizeHint().width())
        body_w = w + 2 * PAD_X
        body_h = h + ch + btn_h + 2 * PAD_Y
        tail = TAIL_W if self.tail in ("left", "right") else 0
        self._body = QRectF((tail if self.tail == "left" else 0) + 1.5, TAB_H + 1.5, body_w, body_h)
        self.setFixedSize(int(body_w + tail + 4), int(body_h + TAB_H + 10))
        if btn_h:
            self.buttons.setGeometry(int(self._body.left() + PAD_X), int(self._body.bottom() - PAD_Y - btn_h + 10),
                                     int(w), int(btn_h - 12))

    # -- painting -----------------------------------------------------------------------------
    def _frame_path(self) -> QPainterPath:
        r, c = self._body, CHAMFER
        if self.side == "capri":   # cut top-right and bottom-left corners
            pts = [QPointF(r.left(), r.top()), QPointF(r.right() - c, r.top()), QPointF(r.right(), r.top() + c),
                   QPointF(r.right(), r.bottom()), QPointF(r.left() + c, r.bottom()), QPointF(r.left(), r.bottom() - c)]
        else:                      # user: cut top-left, top-right and bottom-left
            pts = [QPointF(r.left() + c, r.top()), QPointF(r.right() - c, r.top()), QPointF(r.right(), r.top() + c),
                   QPointF(r.right(), r.bottom()), QPointF(r.left() + c, r.bottom()), QPointF(r.left(), r.bottom() - c),
                   QPointF(r.left(), r.top() + c)]
        poly = QPolygonF(pts)
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        ty = r.top() + 22
        if self.tail == "left":
            t = QPainterPath()
            t.addPolygon(QPolygonF([QPointF(r.left() + 1, ty), QPointF(r.left() - TAIL_W, ty + TAIL_H * 0.55),
                                    QPointF(r.left() + 1, ty + TAIL_H)]))
            path = path.united(t)
        elif self.tail == "right":
            t = QPainterPath()
            t.addPolygon(QPolygonF([QPointF(r.right() - 1, ty), QPointF(r.right() + TAIL_W, ty + TAIL_H * 0.55),
                                    QPointF(r.right() - 1, ty + TAIL_H)]))
            path = path.united(t)
        return path

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._body
        path = self._frame_path()
        fill = theme.BUBBLE if self.side == "capri" else theme.BUBBLE_USER
        p.fillPath(path, theme.rgba(fill, 238))
        p.setPen(QPen(self.color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
        p.drawPath(path)
        self._paint_tabs(p, r)
        # text
        p.setPen(theme.TEXT)
        p.setFont(self._font)
        tr = QRectF(r.left() + PAD_X, r.top() + PAD_Y, r.width() - 2 * PAD_X, r.height() - 2 * PAD_Y)
        if self.thinking:
            dots = "•" * (self._dots or 1) + " " * (3 - (self._dots or 1))
            p.setFont(theme.heading_font(26))
            p.setPen(self.color)
            p.drawText(tr.adjusted(0, -6, 0, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), dots)
            text_h = QFontMetrics(theme.heading_font(26)).height() - 6
        else:
            shown = self.full_text[: self.shown_chars]
            flags = int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            p.drawText(tr, flags, shown)
            text_h = QFontMetrics(self._font).boundingRect(0, 0, int(tr.width()), 10000, int(Qt.TextFlag.TextWordWrap),
                                                          self.full_text or " ").height()
        if self.caption:
            p.setFont(self._cap_font)
            p.setPen(theme.SECONDARY)
            cr = QRectF(tr.left(), tr.top() + text_h + 6, tr.width(), 1000)
            p.drawText(cr, int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                       self.caption)
        p.end()

    def _paint_tabs(self, p: QPainter, r: QRectF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        top = r.top() - TAB_H + 1
        if self.side == "capri":
            x = r.left() + 6
            p.setBrush(theme.GREEN)
            p.drawPolygon(QPolygonF([QPointF(x, top + TAB_H), QPointF(x + 6, top), QPointF(x + 58, top),
                                     QPointF(x + 52, top + TAB_H)]))
            x += 62
            p.setBrush(theme.SECONDARY)
            for i in range(3):
                xs = x + i * 9
                p.drawPolygon(QPolygonF([QPointF(xs, top + TAB_H), QPointF(xs + 6, top), QPointF(xs + 10, top),
                                         QPointF(xs + 4, top + TAB_H)]))
            x += 32
            p.drawPolygon(QPolygonF([QPointF(x, top + TAB_H), QPointF(x + 8, top), QPointF(x + 20, top),
                                     QPointF(x + 28, top + TAB_H)]))
        else:
            x = r.right() - 8
            p.setBrush(theme.GREEN)
            p.drawPolygon(QPolygonF([QPointF(x - 70, top + TAB_H), QPointF(x - 64, top), QPointF(x, top),
                                     QPointF(x, top + TAB_H)]))
            p.setBrush(theme.PINK)
            p.drawPolygon(QPolygonF([QPointF(x - 104, top + TAB_H), QPointF(x - 98, top), QPointF(x - 76, top),
                                     QPointF(x - 82, top + TAB_H)]))
            # purple stripes under the bottom-right corner
            p.setBrush(theme.PURPLE)
            b = r.bottom() + 1
            for i in range(3):
                xs = r.right() - 60 + i * 14
                p.drawPolygon(QPolygonF([QPointF(xs, b), QPointF(xs + 10, b), QPointF(xs + 18, b + 7),
                                         QPointF(xs + 8, b + 7)]))
