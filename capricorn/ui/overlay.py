"""The floating overlay: Capri + speech bubble, always on top, never steals focus."""
from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QWidget

from ..config import Settings
from .bubble import Bubble
from .sprite import Sprite

GAP = 4


class Overlay(QWidget):
    open_chat = pyqtSignal()
    answered = pyqtSignal(bool)
    context_menu = pyqtSignal(object)   # QPoint

    def __init__(self, settings: Settings) -> None:
        super().__init__(None)
        self.s = settings
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Capri")
        scale = float(settings.get("ui.scale", 0.42))
        self.sprite = Sprite(scale, float(settings.get("ui.minimal_scale", 0.36)),
                             str(settings.get("ui.mode", "normal")))
        self.sprite.setParent(self)
        self.sprite.dragged.connect(self._on_drag)
        self.sprite.drag_finished.connect(self._save_pos)
        self.sprite.clicked.connect(self.open_chat.emit)
        self.bubble = Bubble("capri", tail="right", max_text_width=int(300 + 120 * scale), font_px=16)
        self.bubble.setParent(self)
        self.bubble.answered.connect(self.answered.emit)
        self.bubble.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.fade_out)
        self._raise_timer = QTimer(self)
        self._raise_timer.timeout.connect(self._keep_on_top)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(260)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_hiding = False
        self._fade.finished.connect(self._fade_done)
        self.mode = "hidden"     # hidden | listening | thinking | reply | confirm | idle
        self.menu_open = False
        self._anchor = self._default_anchor()
        self._relayout()

    # -- placement ------------------------------------------------------------------------------
    def _screen_rect(self):
        scr = QGuiApplication.screenAt(self._anchor) if hasattr(self, "_anchor") else None
        scr = scr or QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    def _default_anchor(self) -> QPoint:
        """Top-left of the sprite, in screen coordinates."""
        xy = self.s.get("ui.custom_xy")
        scr = QGuiApplication.primaryScreen().availableGeometry()
        if self.s.get("ui.position") == "custom" and isinstance(xy, (list, tuple)) and len(xy) == 2:
            p = QPoint(int(xy[0]), int(xy[1]))
            if any(s.availableGeometry().contains(p) for s in QGuiApplication.screens()):
                return p
        m = int(self.s.get("ui.margin", 24))
        w = h = self.sprite.width()
        pos = str(self.s.get("ui.position", "bottom-right"))
        x = scr.left() + m if "left" in pos else scr.right() - w - m
        y = scr.top() + m if "top" in pos else scr.bottom() - h - m
        return QPoint(x, y)

    def _capri_on_right(self) -> bool:
        scr = self._screen_rect()
        return self._anchor.x() + self.sprite.width() / 2 > scr.center().x()

    def _relayout(self) -> None:
        sw, sh = self.sprite.width(), self.sprite.height()
        bvis = not self.bubble.isHidden()
        bw, bh = (self.bubble.width(), self.bubble.height()) if bvis else (0, 0)
        on_right = self._capri_on_right()
        self.bubble.tail = "right" if on_right else "left"
        top_off = int(sh * 0.12)
        height = max(sh, bh + top_off)
        width = sw + (bw + GAP if bvis else 0)
        sprite_y = height - sh
        bubble_y = max(0, sprite_y + top_off - max(0, bh + top_off - sh))
        if on_right:
            sx, bx = width - sw, 0
        else:
            sx, bx = 0, sw + GAP
        self.sprite.move(sx, sprite_y)
        self.bubble.move(bx, bubble_y)
        self.setFixedSize(width, height)
        self.move(self._anchor.x() - sx, self._anchor.y() - sprite_y)

    def _on_drag(self, delta) -> None:
        self._anchor += delta
        self._relayout()

    def _save_pos(self) -> None:
        try:
            self.s.set_and_save("ui.position", "custom")
            self.s.set_and_save("ui.custom_xy", [self._anchor.x(), self._anchor.y()])
        except Exception:
            pass

    def reset_position(self) -> None:
        self.s.set_and_save("ui.position", "bottom-right")
        self._anchor = self._default_anchor()
        self._relayout()

    # -- look / visibility -----------------------------------------------------------------------
    @property
    def minimal(self) -> bool:
        return self.sprite.mode == "minimal"

    def always_visible(self) -> bool:
        if self.minimal:
            return bool(self.s.get("ui.minimal_always_visible", True))
        return bool(self.s.get("ui.always_visible", False))

    def set_mode(self, mode: str) -> None:
        """Switch between the normal look and minimal mode (saved to settings)."""
        old = self.sprite.size()
        bottom_right = self._anchor + QPoint(old.width(), old.height())
        self.s.set_and_save("ui.mode", mode)
        self.sprite.set_mode(mode)
        new = self.sprite.size()
        self._anchor = bottom_right - QPoint(new.width(), new.height())
        self.bubble.hide()
        self.mode = "idle"
        self._relayout()
        if self.always_visible():
            self.show_idle()

    def apply_size(self) -> None:
        """Size / position settings changed: apply without a restart."""
        old = self.sprite.size()
        bottom_right = self._anchor + QPoint(old.width(), old.height())
        scale = float(self.s.get("ui.scale", 0.42))
        self.sprite.set_scale(scale, float(self.s.get("ui.minimal_scale", 0.36)))
        self.bubble.max_text_width = int(300 + 120 * scale)
        new = self.sprite.size()
        if str(self.s.get("ui.position", "bottom-right")) == "custom":
            self._anchor = bottom_right - QPoint(new.width(), new.height())
        else:
            self._anchor = self._default_anchor()
        self._relayout()

    def set_always_visible(self, on: bool) -> None:
        key = "ui.minimal_always_visible" if self.minimal else "ui.always_visible"
        self.s.set_and_save(key, bool(on))
        if on:
            self.show_idle()
        else:
            self.hide_soon(2500)

    def set_music(self, playing: bool) -> None:
        self.sprite.set_music(playing)

    # -- states -------------------------------------------------------------------------------------
    def _appear(self) -> None:
        self._hide_timer.stop()
        if self._fade_hiding:
            self._fade.stop()
            self._fade_hiding = False
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        else:
            self.setWindowOpacity(1.0)
        self.raise_()
        self._raise_timer.start(1500)

    def show_listening(self, text: str = "Listening...", caption: str = "") -> None:
        was_hidden = not self.isVisible()
        self.mode = "listening"
        if self.minimal:
            self.bubble.hide()
            self.sprite.glitch(then="__idle__")      # quick glitch = "I heard you"
        else:
            if was_hidden:
                self.sprite.glitch(then="surprised")  # glitch in, then the surprised pose
            else:
                self.sprite.set_pose("surprised")
            self.bubble.show()
            self.bubble.set_text(text, caption=caption, typewriter=False)
        self._relayout()
        self._appear()
        self._hide_timer.start(15000)   # safety net

    def show_thinking(self, caption: str = "") -> None:
        self.mode = "thinking"
        if self.minimal:
            self.bubble.hide()
            self._relayout()
            self._appear()
            self._hide_timer.start(90000)
            return
        self.sprite.set_pose("thinking")
        self.bubble.show()
        self.bubble.set_thinking(caption)
        self._relayout()
        self._appear()
        self._hide_timer.start(90000)

    def show_reply(self, text: str, emotion: str = "smile", caption: str = "", ask: bool = False) -> None:
        self.mode = "confirm" if ask else "reply"
        self._reply_emotion = emotion
        cps = int(self.s.get("ui.typewriter_cps", 45))
        if self.minimal and not ask:
            # minimal mode: no bubble - just the talking face (the text is in the chat window)
            self.bubble.hide()
            self._relayout()
            self._appear()
            talk_ms = int(1000 * len(text) / max(5, cps))
            self.sprite.talk_for(talk_ms, then=emotion)
            if not self.always_visible():
                self._hide_timer.start(talk_ms + int(float(self.s.get("ui.hide_after", 9.0)) * 1000))
            else:
                self._hide_timer.start(talk_ms + 1500)    # -> back to idle
            return
        self.bubble.show()
        self.bubble.set_text(text, caption=caption, typewriter=True, cps=cps, ask=ask)
        self._relayout()
        self._appear()
        self.sprite.talk_for(self.bubble.typing_duration_ms(), then=emotion)
        if not ask:
            hide = float(self.s.get("ui.hide_after", 9.0)) * 1000 + self.bubble.typing_duration_ms()
            self._hide_timer.start(int(hide))
        else:
            self._hide_timer.start(30000)

    def set_hint(self, text: str) -> None:
        """Small caption under the current reply, e.g. '● listening...' during a follow-up."""
        if self.bubble.isVisible() and self.mode in {"reply", "confirm"}:
            self.bubble.set_caption(text)
            self._relayout()
        if text and self._hide_timer.isActive():
            self._hide_timer.start(max(self._hide_timer.remainingTime(), 9000))

    def speaking(self, ms: int) -> None:
        """Capri's voice is playing `ms` of audio: lip-sync the talking loop to it and keep the
        reply on screen until she has finished (plus the usual linger time)."""
        if self.mode not in {"reply", "confirm"} or not self.isVisible():
            return
        self.sprite.talk_for(ms, then=getattr(self, "_reply_emotion", "smile"))
        if self.mode == "confirm":
            return
        if self.minimal and self.always_visible():
            linger = 1500
        else:
            linger = int(float(self.s.get("ui.hide_after", 9.0)) * 1000)
        left = self._hide_timer.remainingTime() if self._hide_timer.isActive() else 0
        self._hide_timer.start(max(left, ms + linger))

    def show_idle(self) -> None:
        self.mode = "idle"
        self.bubble.hide()
        self.sprite.idle()
        self._relayout()
        self._appear()

    def hide_soon(self, ms: int = 1200) -> None:
        self._hide_timer.start(ms)

    def cancel_listening(self) -> None:
        if self.mode in {"listening", "thinking"}:
            self.fade_out()

    def fade_out(self) -> None:
        if self.underMouse() and self.mode in {"reply", "confirm"}:
            self._hide_timer.start(2500)
            return
        if self.always_visible():
            self.show_idle()
            return
        if not self.isVisible():
            self.mode = "hidden"
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade_hiding = True
        self._fade.start()

    def _fade_done(self) -> None:
        if self._fade_hiding:
            self._fade_hiding = False
            self.hide()
            self._raise_timer.stop()
            self.mode = "hidden"
            self.bubble.hide()
            self.sprite.idle()

    def _keep_on_top(self) -> None:
        # never cover an open menu (tray / right-click), Qt popups are separate windows
        from PyQt6.QtWidgets import QApplication
        if self.isVisible() and not self.menu_open and QApplication.activePopupWidget() is None:
            self.raise_()

    # -- events ---------------------------------------------------------------------------------------
    def enterEvent(self, e) -> None:
        if self.mode in {"reply", "confirm"} and self._hide_timer.isActive():
            self._hide_timer.start(max(self._hide_timer.remainingTime(), 4000))
        super().enterEvent(e)

    def contextMenuEvent(self, e) -> None:
        self.context_menu.emit(e.globalPos())
