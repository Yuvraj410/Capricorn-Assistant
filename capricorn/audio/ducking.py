"""Audio ducking: while Capri is listening / talking, every OTHER app's volume (music, videos, games)
is lowered, then restored - like Google Assistant on a phone.

Uses Windows' per-app volume mixer (Core Audio sessions via pycaw), so the system volume and
Capri's own sounds are untouched. Safety nets so volumes are never left low:
  * the original volumes are written to capricorn-data/ducked.json and restored on the next start
    if Capri crashed while ducking;
  * restore() only touches a session if its volume is still what we set (if you changed it by hand
    meanwhile, your choice wins);
  * a watchdog restores everything after `max_seconds` no matter what.
All COM work happens on one dedicated thread.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time

from .. import paths

log = logging.getLogger(__name__)
STATE_FILE = "ducked.json"


class Ducker:
    def __init__(self, level: float = 0.25, fade_ms: int = 180, max_seconds: float = 60.0,
                 enabled: bool = True) -> None:
        self.level = max(0.0, min(1.0, level))
        self.fade_ms = fade_ms
        self.max_seconds = max_seconds
        self.enabled = enabled and sys.platform == "win32"
        self._q: "queue.Queue[str]" = queue.Queue()
        self._ducked: dict[str, tuple[float, float]] = {}    # key -> (original, ducked value)
        self._since = 0.0
        self.available = True
        self._started = False
        if self.enabled:
            self._start()

    def _start(self) -> None:
        if not self._started:
            self._started = True
            threading.Thread(target=self._loop, daemon=True, name="ducker").start()
            self._q.put("recover")

    def set_enabled(self, on: bool) -> None:
        if not on and self._ducked:
            self.restore()
        self.enabled = on and sys.platform == "win32"
        if self.enabled:
            self._start()

    # -- public (any thread) -----------------------------------------------------------------------
    def duck(self) -> None:
        if self.enabled and self.available:
            self._q.put("duck")

    def restore(self) -> None:
        if self.enabled and self.available:
            self._q.put("restore")

    def restore_now(self) -> None:
        """Blocking restore (app exit)."""
        if not self.enabled or not self._ducked:
            return
        done = threading.Event()
        self._q.put("restore")
        self._q.put("signal")
        self._done = done
        done.wait(2.0)

    @property
    def is_ducked(self) -> bool:
        return bool(self._ducked)

    # -- worker thread -----------------------------------------------------------------------------
    def _loop(self) -> None:
        try:
            import comtypes  # type: ignore
            comtypes.CoInitialize()
            from pycaw.pycaw import AudioUtilities  # type: ignore
        except Exception as e:
            self.available = False
            log.warning("audio ducking unavailable (%s) - run update.bat to install pycaw", e)
            return
        self._au = AudioUtilities
        while True:
            try:
                cmd = self._q.get(timeout=1.0)
            except queue.Empty:
                if self._ducked and time.time() - self._since > self.max_seconds:
                    log.info("ducking watchdog: restoring volumes")
                    self._do_restore()
                continue
            try:
                if cmd == "duck":
                    self._do_duck()
                elif cmd == "restore":
                    self._do_restore()
                elif cmd == "recover":
                    self._recover()
                elif cmd == "signal":
                    getattr(self, "_done", threading.Event()).set()
            except Exception:
                log.exception("ducking %s failed", cmd)

    def _sessions(self) -> dict[str, object]:
        me = os.getpid()
        out = {}
        for s in self._au.GetAllSessions():
            try:
                pid = s.ProcessId
                if not pid or pid == me:          # 0 = Windows system sounds; me = Capri's voice/chimes
                    continue
                name = s.Process.name() if s.Process else str(pid)
                out[f"{name}:{pid}"] = s.SimpleAudioVolume
            except Exception:
                continue
        return out

    def _fade(self, plan: list[tuple[object, float, float]]) -> None:
        steps = max(1, self.fade_ms // 30)
        for i in range(1, steps + 1):
            f = i / steps
            for vol, a, b in plan:
                try:
                    vol.SetMasterVolume(a + (b - a) * f, None)
                except Exception:
                    pass
            time.sleep(0.03)

    def _do_duck(self) -> None:
        self._since = time.time()
        if self._ducked:
            return                                  # already down; keep the original values
        plan = []
        for key, vol in self._sessions().items():
            try:
                cur = float(vol.GetMasterVolume())
            except Exception:
                continue
            if cur <= 0.01:
                continue
            target = round(cur * self.level, 4)
            self._ducked[key] = (cur, target)
            plan.append((vol, cur, target))
        self._save()
        self._fade(plan)
        if plan:
            log.info("ducked %d app(s): %s", len(plan), ", ".join(k.split(":")[0] for k in self._ducked))

    def _do_restore(self) -> None:
        if not self._ducked:
            return
        sessions = self._sessions()
        plan = []
        for key, (orig, target) in self._ducked.items():
            vol = sessions.get(key)
            if vol is None:
                continue
            try:
                cur = float(vol.GetMasterVolume())
            except Exception:
                continue
            if abs(cur - target) < 0.02:            # untouched by the user meanwhile
                plan.append((vol, cur, orig))
        self._fade(plan)
        self._ducked.clear()
        self._save()
        log.info("restored %d app volume(s)", len(plan))

    def _recover(self) -> None:
        """Capri crashed while ducking last time -> put those volumes back."""
        p = paths.user_dir() / STATE_FILE
        if not p.exists():
            return
        try:
            saved = {k: tuple(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
        except Exception:
            saved = {}
        if saved:
            self._ducked = saved
            self._do_restore()
            log.info("recovered volumes left ducked by a previous run")
        p.unlink(missing_ok=True)

    def _save(self) -> None:
        p = paths.user_dir() / STATE_FILE
        try:
            if self._ducked:
                p.write_text(json.dumps(self._ducked), encoding="utf-8")
            else:
                p.unlink(missing_ok=True)
        except OSError:
            pass
