"""Capri's character: emotion poses + frame animations (assets/character/manifest.json).

Two looks:
  normal  - full character: emotion poses, blink, talking, dance (music), glitch (appearing)
  minimal - just the visor face: min_idle (loops), min_glitch (every so often), min_talking
"""
from __future__ import annotations

import json
import logging
import random

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel

from .. import paths

log = logging.getLogger(__name__)

DPR = 2.0   # frames are rendered at 2x for crisp HiDPI


class Sprite(QLabel):
    dragged = pyqtSignal(object)      # QPoint delta
    drag_finished = pyqtSignal()
    clicked = pyqtSignal()

    def __init__(self, scale: float = 0.42, minimal_scale: float = 0.36, mode: str = "normal") -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scale, self._min_scale = scale, minimal_scale
        self.poses: dict[str, QPixmap] = {}
        self.anims: dict[str, tuple[list[QPixmap], list[int]]] = {}
        self._min_size = QSize(int(512 * minimal_scale), int(512 * minimal_scale * 288 / 501))
        self._load()
        self.mode = "normal"
        self.current = "neutral"
        self.music = False             # dance while music plays (normal look only)
        self.busy = False              # talking/thinking - don't switch to idle/dance
        self._anim_name: str | None = None
        self._anim_i = 0
        self._anim_loop = False
        self._after_anim = "neutral"
        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self._next_frame)
        self._idle_fx = QTimer(self)        # blink (normal) / glitch (minimal)
        self._idle_fx.setSingleShot(True)
        self._idle_fx.timeout.connect(self._idle_effect)
        self._talk_end = QTimer(self)
        self._talk_end.setSingleShot(True)
        self._talk_end.timeout.connect(self._end_talk)
        self._talk_then = "neutral"
        self._press = None
        self._moved = False
        self.set_mode(mode)

    # -- loading -------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            manifest = json.loads((paths.CHARACTER_DIR / "manifest.json").read_text(encoding="utf-8"))
        except Exception:
            log.exception("character manifest missing")
            manifest = {"poses": {}, "animations": {}}
        normal = int(512 * self._scale)

        def load(name: str, box: QSize) -> QPixmap:
            pm = QPixmap(str(paths.CHARACTER_DIR / name))
            if pm.isNull():
                return pm
            pm = pm.scaled(QSize(int(box.width() * DPR), int(box.height() * DPR)),
                           Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(DPR)
            return pm

        for pose, file in manifest.get("poses", {}).items():
            pm = load(file, QSize(normal, normal))
            if not pm.isNull():
                self.poses[pose] = pm
        for name, a in manifest.get("animations", {}).items():
            box = self._min_size if name.startswith("min_") else QSize(normal, normal)
            frames = [load(f, box) for f in a.get("frames", [])]
            frames = [f for f in frames if not f.isNull()]
            if frames:
                durs = list(a.get("durations_ms", []))
                durs += [120] * (len(frames) - len(durs))
                self.anims[name] = (frames, durs)
        self._normal_size = QSize(normal, normal)

    def set_scale(self, scale: float, minimal_scale: float) -> None:
        """Resize Capri live (settings screen)."""
        self._scale, self._min_scale = scale, minimal_scale
        self._min_size = QSize(int(512 * minimal_scale), int(512 * minimal_scale * 288 / 501))
        self.poses.clear()
        self.anims.clear()
        self._load()
        self.set_mode(self.mode)

    def has(self, anim: str) -> bool:
        return anim in self.anims

    # -- modes -------------------------------------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        self.mode = "minimal" if mode == "minimal" and self.has("min_idle") else "normal"
        self.setFixedSize(self._min_size if self.mode == "minimal" else self._normal_size)
        self.busy = False
        self.idle()

    def idle(self) -> None:
        """Resting animation for the current look (dances instead if music is playing)."""
        self._talk_end.stop()
        if self.mode == "minimal":
            if self.music and self.has("min_dance"):
                self.play("min_dance", loop=True)
            else:
                self.play("min_idle", loop=True)
        else:
            if self.music and self.has("dance"):
                self.play("dance", loop=True)
            else:
                self.set_pose("neutral")
        self._schedule_idle_fx()

    def set_music(self, playing: bool) -> None:
        if playing == self.music:
            return
        self.music = playing
        if not self.busy and (self._anim_name in {None, "dance", "min_idle", "min_dance", "blink"}):
            self.idle()

    def glitch(self, then: str | None = None) -> None:
        """Glitch effect (appearing / every so often in minimal mode)."""
        name = "min_glitch" if self.mode == "minimal" else "glitch"
        if self.has(name):
            self.play(name, loop=False, then=then or ("__idle__" if self.mode == "minimal" else self.current))
        elif then:
            self._go(then)

    # -- poses & animations -------------------------------------------------------------------
    def set_pose(self, pose: str) -> None:
        if self.mode == "minimal":           # no emotion poses in the minimal look
            if self._anim_name not in {"min_idle", "min_dance"}:
                self.play("min_dance" if self.music and self.has("min_dance") else "min_idle", loop=True)
            self.current = pose
            return
        self._anim_timer.stop()
        self._anim_name = None
        pm = self.poses.get(pose) or self.poses.get("neutral")
        if pm is not None:
            self.setPixmap(pm)
        self.current = pose

    def show_emotion(self, pose: str) -> None:
        """Show an emotion; after replies we return to idle/dance via idle()."""
        self.busy = False
        if self.mode == "minimal":
            self.idle()
        elif self.music and pose not in {"sad", "angry", "surprised"}:
            self.idle()                      # music is playing -> back to dancing
        else:
            self.set_pose(pose)

    def play(self, name: str, loop: bool = False, then: str | None = None) -> None:
        if name not in self.anims:
            if then:
                self._go(then)
            return
        self._anim_timer.stop()
        self._anim_name, self._anim_i, self._anim_loop = name, 0, loop
        self._after_anim = then or self.current
        self._next_frame()

    def _go(self, target: str) -> None:
        if target == "__idle__":
            self.idle()
        else:
            self.set_pose(target)

    def talk_for(self, ms: int, then: str) -> None:
        """Talking loop for `ms`, then settle on the emotion (normal) / idle (minimal)."""
        self.busy = True
        name = "min_talking" if self.mode == "minimal" else "talking"
        self._talk_then = then
        self.play(name, loop=True, then=then)
        self._talk_end.start(max(500, ms))

    def _end_talk(self) -> None:
        if self._anim_name in {"talking", "min_talking"}:
            self.show_emotion(self._talk_then)
        self.busy = False

    def _next_frame(self) -> None:
        if not self._anim_name:
            return
        frames, durs = self.anims[self._anim_name]
        if self._anim_i >= len(frames):
            if self._anim_loop:
                self._anim_i = 0
            else:
                after = self._after_anim
                self._anim_name = None
                self._go(after)
                return
        self.setPixmap(frames[self._anim_i])
        self._anim_timer.start(durs[self._anim_i])
        self._anim_i += 1

    def _schedule_idle_fx(self) -> None:
        # normal: blink every few seconds; minimal: glitch now and then
        lo, hi = (9000, 22000) if self.mode == "minimal" else (3500, 7500)
        self._idle_fx.start(random.randint(lo, hi))

    def _idle_effect(self) -> None:
        if self.isVisible() and not self.busy:
            if self.mode == "minimal" and self._anim_name == "min_idle":
                self.play("min_glitch", loop=False, then="__idle__")
            elif self.mode == "normal" and self._anim_name is None and self.current == "neutral" and self.has("blink"):
                # skip the blink gif's long first hold frame - just the blink itself
                self._anim_name, self._anim_i, self._anim_loop = "blink", 1, False
                self._after_anim = "neutral"
                self._next_frame()
        self._schedule_idle_fx()

    # -- dragging -------------------------------------------------------------------------------
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        if self._press is not None:
            pos = e.globalPosition().toPoint()
            delta = pos - self._press
            if delta.manhattanLength() > 3:
                self._moved = True
                self._press = pos
                self.dragged.emit(delta)

    def mouseReleaseEvent(self, e) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self._press is not None:
            if self._moved:
                self.drag_finished.emit()
            else:
                self.clicked.emit()
        self._press = None
