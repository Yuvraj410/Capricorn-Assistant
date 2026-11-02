"""Capricorn main application: wires listener → router → overlay/chat/tray."""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from PyQt6.QtCore import QLockFile, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import APP_NAME, __version__, paths, persona
from .actions.base import Result
from .actions.registry import ActionRegistry
from .audio.listener import Callbacks, Listener
from .audio.stt import STT
from .brain.llm import LLM
from .brain.router import Router
from .config import Settings, ensure_user_files
from .security.permissions import Permissions
from .audio.ducking import Ducker
from .tts.engine import TTS, play_sound
from .ui import theme
from .ui.chat_window import ChatWindow
from .ui.hotkey import GlobalHotkey
from .ui.overlay import Overlay

log = logging.getLogger("capricorn")

YES = re.compile(r"\b(yes|yeah|yep|yup|sure|do it|go ahead|confirm|ok|okay|affirmative|please do|absolutely)\b", re.I)
NO = re.compile(r"\b(no|nope|nah|cancel|stop|don't|do not|never ?mind|negative|abort)\b", re.I)


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = RotatingFileHandler(paths.logs_dir() / "capricorn.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:   # pythonw has no console
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


class Bridge(QObject):
    """Thread-safe hop from background threads into the Qt main thread."""
    wake = pyqtSignal()
    wake_cancel = pyqtSignal()
    listening = pyqtSignal()
    transcribing = pyqtSignal()
    command = pyqtSignal(str, str)
    no_command = pyqtSignal()
    capture = pyqtSignal(str, str)
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    result = pyqtSignal(object, str)     # Result, source ("voice"|"chat")
    music = pyqtSignal(bool)             # media playing somewhere -> Capri dances
    speaking = pyqtSignal(int)           # Capri's voice: a clip of N ms starts playing
    spoken = pyqtSignal(int, bool)       # utterance token, completed
    voice_ready = pyqtSignal()
    progress = pyqtSignal(str, str)      # interim line while a slow action runs ("Digging through the Net...")


class CapricornApp:
    def __init__(self, qapp: QApplication) -> None:
        self.qapp = qapp
        self.settings = Settings()
        self.perms = Permissions()
        self.registry = ActionRegistry(self.settings, self.perms)
        self.llm = LLM(self.settings)
        self.router = Router(self.registry, self.llm)
        self.stt = STT(self.settings)
        self.bridge = Bridge()
        self.tts = TTS(self.settings, on_status=self.bridge.status.emit, on_ready=self.bridge.voice_ready.emit)
        self._started_at = time.time()
        self._greeted_out_loud = False
        self._utt = 0                         # token of the reply currently being spoken
        self.ducker = Ducker(level=float(self.settings.get("voice.duck_level", 0.15)),
                             enabled=bool(self.settings.get("voice.duck_others", True)))
        self._unduck_timer = QTimer()
        self._unduck_timer.setSingleShot(True)
        self._unduck_timer.timeout.connect(self.ducker.restore)
        self._after_speech: dict[int, object] = {}
        self.pending: Result | None = None
        self.pending_source = "voice"
        self.status_text = "Starting..."
        self._busy = False

        theme.load_fonts()
        self.qapp.setStyleSheet(theme.STYLESHEET)
        self.overlay = Overlay(self.settings)
        self.chat = ChatWindow()
        self._build_tray()
        self._sync_ui_actions()

        self.overlay.open_chat.connect(self.chat.open)
        self.overlay.answered.connect(lambda yes: self._answer(yes))
        self.overlay.context_menu.connect(self._popup_menu)
        self.chat.submitted.connect(lambda t: self.handle_text(t, "chat"))
        self.chat.answered.connect(lambda yes: self._answer(yes))
        self.chat.settings_requested.connect(self.open_settings)
        self.settings_win = None

        b = self.bridge
        b.wake.connect(self._on_wake)
        b.wake_cancel.connect(self.overlay.cancel_listening)
        b.wake_cancel.connect(lambda: self._unduck_soon(300))
        b.listening.connect(self._on_listening)
        b.transcribing.connect(lambda: self.overlay.show_thinking(""))
        b.command.connect(lambda cmd, heard: self.handle_text(cmd, "voice"))
        b.no_command.connect(self._on_no_command)
        b.capture.connect(self._on_capture)
        b.status.connect(self._set_status)
        b.error.connect(self._on_error)
        b.result.connect(self._present)
        b.music.connect(self.overlay.set_music)
        b.speaking.connect(self.overlay.speaking)
        b.spoken.connect(self._on_spoken)
        b.voice_ready.connect(self._on_voice_ready)
        b.progress.connect(self._on_progress)
        self.router.progress = lambda text, emo="thinking": self.bridge.progress.emit(text, emo)

        cb = Callbacks(on_wake=b.wake.emit, on_wake_cancel=b.wake_cancel.emit, on_listening=b.listening.emit,
                       on_transcribing=b.transcribing.emit, on_command=b.command.emit,
                       on_no_command=b.no_command.emit, on_capture=b.capture.emit,
                       on_status=b.status.emit, on_error=b.error.emit)
        self.listener = Listener(self.settings, self.stt, cb)
        # Whisper hears names it was told about far better ("Black Myth: Wukong", not "blacksmith wukong")
        self.listener.hotwords_fn = lambda: ", ".join(["Hey C", "Capri", "Capricorn", "Capricon"] +
                                                      self.registry.app_index.game_names(25))[:600]

        self.hotkey = GlobalHotkey(str(self.settings.get("ui.hotkey", "ctrl+alt+c")))
        self.hotkey.triggered.connect(self.chat.open)

    # -- startup ------------------------------------------------------------------------------------
    def start(self) -> None:
        self.listener.start()
        self.tts.start()
        self.hotkey.start()
        threading.Thread(target=self._background_init, daemon=True, name="init").start()
        threading.Thread(target=self._music_watch, daemon=True, name="music-watch").start()
        if self.overlay.always_visible():
            self.overlay.show_idle()
        QTimer.singleShot(1200, self._greet)

    def _background_init(self) -> None:
        ok, msg = self.llm.status()
        if ok:
            self.bridge.status.emit("Brain online · say 'Hey Capri'")
            self.llm.warm_up()
        else:
            self.bridge.status.emit(f"Brain offline: {msg}")
        try:
            self.stt.preload()
        except Exception as e:
            log.exception("whisper preload failed")
            self.bridge.error.emit(f"Speech recognition couldn't load: {e}")

    def _music_watch(self) -> None:
        """Poll Windows' media sessions; Capri dances while something is playing."""
        import time as _t
        from .actions.media import is_playing
        last = None
        while True:
            playing = is_playing()
            if playing is None:          # not supported here - stop polling
                return
            if playing != last:
                last = playing
                self.bridge.music.emit(playing)
            _t.sleep(2.5)

    def _greet(self) -> None:
        if self.settings.get("ui.greet_on_start", True):
            text = "Capri's online. Say \"Hey Capri\" when you need me."
            self.overlay.show_reply(text, "smile")
            if self.settings.get("voice.greet_out_loud", True) and self._say(text, "smile"):
                self._greeted_out_loud = True

    def _on_voice_ready(self) -> None:
        """Her voice finished loading: say the greeting if it was shown silently a moment ago."""
        if (self.settings.get("ui.greet_on_start", True) and self.settings.get("voice.greet_out_loud", True)
                and not self._greeted_out_loud and time.time() - self._started_at < 120
                and self.overlay.mode in ("idle", "reply") and not self._busy and self.pending is None):
            self._greeted_out_loud = True
            text = "Capri's online. Say \"Hey Capri\" when you need me."
            if self.overlay.mode == "reply" or self.overlay.isVisible():
                self.overlay.show_reply(text, "smile")
            self._say(text, "smile")

    # -- tray -----------------------------------------------------------------------------------------
    def _build_tray(self) -> None:
        icon = QIcon(str(paths.ASSETS_DIR / "icon.png"))
        self.qapp.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip(f"{APP_NAME} - say 'Hey Capri'")
        m = QMenu()
        self.status_action = QAction("Starting...")
        self.status_action.setEnabled(False)
        m.addAction(self.status_action)
        m.addSeparator()
        m.addAction("Open chat  (Ctrl+Alt+C)", self.chat.open)
        m.addAction("Show Capri", lambda: self.overlay.show_reply(*persona.line("greeting")))
        self.mute_action = QAction("Mute microphone", checkable=True)
        self.mute_action.toggled.connect(self._toggle_mute)
        m.addAction(self.mute_action)
        self.minimal_action = QAction("Minimal mode", checkable=True)
        self.minimal_action.setChecked(self.settings.get("ui.mode", "normal") == "minimal")
        self.minimal_action.toggled.connect(lambda on: self._apply_ui("minimal_on" if on else "minimal_off"))
        m.addAction(self.minimal_action)
        self.visible_action = QAction("Always on screen", checkable=True)
        self.visible_action.toggled.connect(lambda on: self._apply_ui("show" if on else "hide"))
        m.addAction(self.visible_action)
        m.addSeparator()
        m.addAction("Settings...", self.open_settings)
        m.addAction("Open settings folder", lambda: os.startfile(str(paths.user_dir())) if sys.platform == "win32" else None)
        m.addAction("Reload settings && permissions", self._reload)
        m.addAction("Reset Capri's position", self.overlay.reset_position)
        m.addAction("Forget conversation", self.llm.reset)
        m.addAction("Forget remembered approvals", self._forget_approvals)
        m.addSeparator()
        m.addAction(f"Restart {APP_NAME}", self.restart)
        m.addAction(f"Quit {APP_NAME}", self.quit)
        m.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        m.aboutToShow.connect(lambda: self._menu_shown(True))
        m.aboutToHide.connect(lambda: self._menu_shown(False))
        self.menu = m
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._tray_click)
        self.tray.show()

    def _apply_ui(self, op: str) -> None:
        """minimal_on | minimal_off | show | hide - from voice, chat or the tray."""
        ov = self.overlay
        if op == "minimal_on" and not ov.minimal:
            ov.set_mode("minimal")
        elif op == "minimal_off" and ov.minimal:
            ov.set_mode("normal")
        elif op == "show":
            ov.set_always_visible(True)
        elif op == "hide":
            ov.set_always_visible(False)
        elif op == "settings":
            self.open_settings()
        elif op in ("voice_louder", "voice_quieter"):
            cur = float(self.settings.get("voice.volume", 1.0))
            new = round(min(3.0, cur * 1.4) if op == "voice_louder" else max(0.2, cur / 1.4), 2)
            self.settings.set_and_save("voice.volume", new)
            self.tts.set_volume(new)
            log.info("voice volume %s -> %s", cur, new)
        self._sync_ui_actions()

    def _sync_ui_actions(self) -> None:
        for act, val in ((self.minimal_action, self.overlay.minimal),
                         (self.visible_action, self.overlay.always_visible())):
            act.blockSignals(True)
            act.setChecked(val)
            act.blockSignals(False)

    def _popup_menu(self, pos) -> None:
        self.menu.popup(pos)
        self.menu.raise_()

    def _menu_shown(self, shown: bool) -> None:
        self.overlay.menu_open = shown
        t = self.overlay._hide_timer
        if shown and t.isActive():          # don't fade out from under the open menu
            t.start(max(t.remainingTime(), 10000))

    def _tray_click(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.chat.open()

    def _toggle_mute(self, muted: bool) -> None:
        self.listener.set_muted(muted)
        self._set_status("Microphone muted" if muted else "Listening for 'Hey Capri'")

    # -- settings screen ------------------------------------------------------------------------------
    def open_settings(self) -> None:
        if self.settings_win is None:
            from .ui.settings_window import SettingsWindow
            self.settings_win = SettingsWindow(self.settings, speak=self._test_voice, restart=self.restart,
                                               models=self.llm.models)
            self.settings_win.saved.connect(self._settings_saved)
        self.settings_win.open()

    def _test_voice(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.overlay.show_reply(text, "smile")
        if not self._say(text, "smile"):
            self._set_status("Voice isn't ready (or is off) - check Voice > engine.")

    def _settings_saved(self, changes: dict, needs_restart: bool) -> None:
        """Apply saved settings live - each part reloads only what changed."""
        self.settings.reload()
        self.perms.reload()
        ch = set(changes)
        if any(k.startswith("wake.") for k in ch):
            self.listener.reconfigure(ch)
        if any(k.startswith("stt.") for k in ch):
            self.stt.reload()
        if any(k.startswith("voice.") for k in ch):
            self.tts.apply_settings(ch)
            if ch & {"voice.engine", "voice.device", "voice.reference"}:
                self._set_status("Reloading Capri's voice (about 25 s)...")
        if "voice.duck_level" in ch:
            self.ducker.level = float(changes["voice.duck_level"])
        if "voice.duck_others" in ch:
            self.ducker.set_enabled(bool(changes["voice.duck_others"]))
        if "ui.hotkey" in ch:
            self.hotkey.stop()
            self.hotkey = GlobalHotkey(str(self.settings.get("ui.hotkey", "ctrl+alt+c")))
            self.hotkey.triggered.connect(self.chat.open)
            self.hotkey.start()
        if ch & {"ui.scale", "ui.minimal_scale", "ui.position", "ui.margin"} and hasattr(self.overlay, "apply_size"):
            self.overlay.apply_size()
        if "ui.mode" in changes:
            self._apply_ui("minimal_on" if changes["ui.mode"] == "minimal" else "minimal_off")
        if "ui.always_visible" in changes or "ui.minimal_always_visible" in changes:
            self.overlay.set_always_visible(self.overlay.always_visible())
        if not (ch & {"voice.engine", "voice.device", "voice.reference"}):
            self._set_status("Settings saved and applied")

    def bring_up(self) -> None:
        """Capricorn was opened again while running (taskbar / Start / Capricorn.exe): show the chat."""
        self.chat.open()
        self.overlay.show_reply(*persona.line("greeting"))

    def restart(self) -> None:
        """Start a fresh Capri a moment after this one has quit (frees the single-instance lock)."""
        import subprocess
        bat = paths.REPO_DIR / "Capricorn.bat"
        if sys.platform == "win32" and bat.exists():
            subprocess.Popen(f'cmd /c timeout /t 3 /nobreak >nul & "{bat}"', cwd=str(paths.REPO_DIR),
                             creationflags=0x00000008 | 0x08000000)    # DETACHED_PROCESS | CREATE_NO_WINDOW
        self.quit()

    def _reload(self) -> None:
        self.settings.reload()
        self.perms.reload()
        self.registry.app_index.refresh_async()
        self.overlay.show_reply("Settings reloaded. Preem.", "smile")

    def _forget_approvals(self) -> None:
        self.perms.forget_approvals()
        self.overlay.show_reply("Wiped. I'll ask again before opening things.", "neutral")

    def _set_status(self, text: str) -> None:
        self.status_text = text
        self.status_action.setText(text[:80])
        self.chat.set_status(text)
        self.tray.setToolTip(f"{APP_NAME} - {text}"[:127])

    def _on_error(self, msg: str) -> None:
        log.error(msg)
        self._set_status(msg)
        self.overlay.show_reply(msg, "sad")
        self.chat.add_capri(msg)
        self._unduck_soon(1500)

    # -- voice flow ---------------------------------------------------------------------------------
    def _on_wake(self) -> None:
        if self.settings.get("sounds.wake_chime", True):
            play_sound("wake")
        self._utt += 1                 # interrupts whatever she was saying (and its follow-up)
        self.tts.stop()
        self._duck()
        self.overlay.show_listening("Listening...")

    def _on_progress(self, text: str, emo: str) -> None:
        """A slow action is running (web lookup): say so, so the silence doesn't feel broken."""
        self.overlay.show_thinking(text)
        if self.tts.instant(text, emo):
            self._say(text, emo, after=lambda: None)

    def _on_listening(self) -> None:
        """'Hey Capri' with no command yet: prompt (out loud when the clip is ready instantly -
        a slow prompt would talk over the start of your command)."""
        text, emo = persona.line("listening")
        self.overlay.show_listening(text)
        if self.settings.get("voice.speak_prompts", True) and self.tts.instant(text, emo):
            self._say(text, emo, after=lambda: None)      # keep other apps ducked: we're still listening

    def _on_no_command(self) -> None:
        text, emo = persona.line("not_understood")
        self.overlay.show_reply(text, emo)
        if not self._say(text, emo):
            self._unduck_soon(1500)

    # -- ducking: other apps get quieter while Capri listens / talks -----------------------------
    def _duck(self) -> None:
        self._unduck_timer.stop()
        self.ducker.duck()

    def _unduck_soon(self, ms: int = 600) -> None:
        if self.pending is not None:          # still waiting for a yes/no
            return
        self._unduck_timer.start(ms)

    # -- handling text (voice or typed) -----------------------------------------------------------
    def handle_text(self, text: str, source: str) -> None:
        text = text.strip()
        if not text:
            return
        log.info("command (%s): %r", source, text)
        if self.pending is not None:      # an open question: treat this as the answer
            if YES.search(text) or NO.search(text):
                self.chat.add_user(text)
                self._answer(bool(YES.search(text)) and not NO.search(text))
                return
            self._clear_pending()
        self.chat.add_user(text)
        if source == "voice" or self.overlay.isVisible():
            caption = f"“{text}”" if self.settings.get("ui.show_user_text", True) else ""
            self.overlay.show_thinking(caption)
        threading.Thread(target=self._work, args=(text, source), daemon=True, name="router").start()

    def _work(self, text: str, source: str) -> None:
        try:
            r = self.router.handle(text)
        except Exception:
            log.exception("router crashed")
            r = Result(False, *persona.line("error"))
        self.bridge.result.emit(r, source)

    def _present(self, r: Result, source: str) -> None:
        if r.confirm_question:
            self.pending, self.pending_source = r, source
            text = (r.say + " " if r.say else "") + r.confirm_question
            hint = "Say yes or no" + (" - I'll remember a yes" if r.approve and r.approve[1] and
                                       self.settings.get("confirmations.remember", True) and
                                       r.approve[1] not in {"sleep", "shutdown", "restart"} else "")
            self.overlay.show_reply(text, "surprised", caption=hint, ask=True)
            self.chat.add_capri(text, ask=True)
            if source == "voice":
                # listen for the yes/no only after she has finished asking (or she'd hear herself)
                capture = lambda: self._start_followup("confirm")
                if not self._say(text, "surprised", after=capture):
                    capture()
            else:
                self._say(text, "surprised")
            return
        text = r.say or "..."
        op = r.data.get("ui")
        if op:
            self._apply_ui(op)
        srcs = r.data.get("sources") or []
        self.chat.add_capri(text + ("\n\nSources: " + ", ".join(d for d, _ in srcs) if srcs else ""))
        show_overlay = source == "voice" or not self.chat.isActiveWindow()
        if show_overlay:
            self.overlay.show_reply(text, r.emotion or "smile", caption=r.data.get("caption", ""))
        converse = (source == "voice" and not r.data.get("dismiss") and not r.data.get("end")
                    and op not in ("hide", "settings") and self.settings.get("conversation.follow_up", True))
        after = (lambda: self._start_followup("followup", question=text.rstrip().endswith("?"))) if converse else None
        if not self._say(text, r.emotion or "smile", after=after):
            if after:
                after()                    # no voice: start listening for a reply right away
            else:
                self._unduck_soon(1200)    # give the music back
        if r.data.get("dismiss") or op == "hide":
            self.overlay.hide_soon(2500 if not self.overlay.minimal else 4000)

    # -- voice output -------------------------------------------------------------------------------
    def _say(self, text: str, emotion: str = "", after=None) -> bool:
        """Speak a reply. Returns False if nothing will be said (then `after` is NOT run)."""
        self._utt += 1
        tok = self._utt
        mute = bool(self.settings.get("voice.mute_mic_while_speaking", True))

        def on_chunk(ms: int) -> None:
            if mute:
                self.listener.hold_speaking()
            self.bridge.speaking.emit(ms)

        def on_done(completed: bool) -> None:
            if tok == self._utt:
                self.listener.release_speaking(0.25)
            self.bridge.spoken.emit(tok, completed)

        if after is not None:
            self._after_speech[tok] = after
        if self.tts.speak(text, emotion, on_chunk=on_chunk, on_done=on_done):
            return True
        self._after_speech.pop(tok, None)
        return False

    def _on_spoken(self, tok: int, completed: bool) -> None:
        fn = self._after_speech.pop(tok, None)
        if fn is not None and tok == self._utt:
            fn()
        elif tok == self._utt:
            self._unduck_soon(500)

    # -- conversation: answer without saying "Capri" again ---------------------------------------
    def _start_followup(self, kind: str = "followup", question: bool = False) -> None:
        """After Capri replies, keep listening for a few seconds - just talk, no wake word."""
        if kind == "followup" and not self.settings.get("conversation.follow_up", True):
            self._unduck_soon(500)
            return
        secs = float(self.settings.get("conversation.answer_seconds" if (question or kind == "confirm")
                                       else "conversation.follow_up_seconds", 8.0 if question else 5.0))
        self._followup_active = True
        self.overlay.set_hint("● listening - just answer")
        self._set_status("Listening for your reply...")
        self.listener.request_capture(kind, timeout=secs)

    def _end_followup(self) -> None:
        if getattr(self, "_followup_active", False):
            self._followup_active = False
            self.overlay.set_hint("")
            self._set_status("Say 'Hey Capri' when you need me")

    def _on_capture(self, kind: str, text: str) -> None:
        self._end_followup()
        from .audio.listener import is_filler
        from .audio.stt import is_hallucination
        heard = (text or "").strip()
        if not heard or is_filler(heard) or is_hallucination(heard):
            if kind == "confirm" and self.pending is not None:
                self._answer(False, silent_reason="No answer - cancelled.")
            else:
                self._unduck_soon(400)          # conversation over; music back up
            return
        if kind == "confirm" and self.pending is not None and not (YES.search(heard) or NO.search(heard)):
            self._clear_pending()               # they said something else entirely: treat it as a new request
        self.handle_text(heard, "voice")

    def _answer(self, yes: bool, silent_reason: str = "") -> None:
        r, src = self.pending, self.pending_source
        self._clear_pending()
        if r is None:
            return
        if yes and r.confirm_run:
            remembered = False
            if r.approve and self.settings.get("confirmations.remember", True):
                remembered = self.perms.remember(*r.approve)

            def run() -> None:
                try:
                    out = r.confirm_run()
                except Exception:
                    log.exception("confirmed action failed")
                    out = Result(False, *persona.line("error"))
                if remembered and out.ok:
                    out.data["caption"] = "Remembered - I won't ask about this again."
                self.bridge.result.emit(out, src)
            threading.Thread(target=run, daemon=True).start()
        else:
            text, emo = (silent_reason, "neutral") if silent_reason else persona.line("cancelled")
            self.bridge.result.emit(Result(True, text, emo), src)

    def _clear_pending(self) -> None:
        self.pending = None
        self.chat.close_question()

    # -- shutdown ---------------------------------------------------------------------------------------
    def quit(self) -> None:
        self.ducker.restore_now()
        self.tts.close()
        self.listener.stop()
        self.hotkey.stop()
        self.tray.hide()
        self.qapp.quit()


INSTANCE_KEY = "Capricorn.Assistant.instance"
APP_ID = "Capricorn.Assistant"


def _start_menu_shortcut() -> None:
    """Start menu > Capricorn (pin it to the taskbar from there). Carries the same app ID as the running
    windows, so the pinned icon and the open chat window share one taskbar button."""
    exe = paths.user_dir() / "python" / "Scripts" / "Capricorn.exe"
    if not exe.exists():
        return
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon
        from win32com.shell import shell
        appdata = os.environ.get("APPDATA", "")
        lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Capricorn.lnk")
        pythoncom.CoInitialize()
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                          shell.IID_IShellLink)
        link.SetPath(str(exe))
        link.SetWorkingDirectory(str(paths.REPO_DIR))
        link.SetIconLocation(str(paths.ASSETS_DIR / "icon.ico"), 0)
        link.SetDescription("Capricorn - say 'Hey Capri'")
        store = link.QueryInterface(propsys.IID_IPropertyStore)
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
        store.Commit()
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(lnk, 0)
        log.info("Start menu shortcut ready: %s", lnk)
    except Exception:
        log.warning("couldn't create the Start menu shortcut", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="capricorn", description="Capricorn desktop assistant")
    ap.add_argument("--profile", choices=["safe", "full"], help="write a permissions profile and exit")
    ap.add_argument("--check", action="store_true", help="check models / Ollama / microphone and exit")
    ap.add_argument("--forget-approvals", action="store_true", help="forget every remembered 'yes' and exit")
    ap.add_argument("--set", metavar="KEY=VALUE", action="append",
                    help="change a setting and exit, e.g. --set brain.model=qwen3:8b  (repeatable)")
    ap.add_argument("--get", metavar="KEY", help="print a setting and exit, e.g. --get brain.model")
    ap.add_argument("--settings", action="store_true", help="open the settings screen (without starting Capri)")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = ap.parse_args(argv)

    setup_logging()
    ensure_user_files(args.profile)
    if args.profile:
        print(f"Permissions set to '{args.profile}' -> {paths.user_dir() / paths.PERMISSIONS_FILE}")
        return 0
    if args.forget_approvals:
        Permissions().forget_approvals()
        print("Remembered approvals cleared - Capri will ask again.")
        return 0
    if args.set:
        import yaml
        st = Settings()
        for item in args.set:
            if "=" not in item:
                print(f"Expected KEY=VALUE, got {item!r}")
                return 2
            key, raw = item.split("=", 1)
            value = yaml.safe_load(raw) if raw.strip() else ""
            st.set_and_save(key.strip(), value)
            print(f"{key.strip()} = {value!r}")
        return 0
    if args.get:
        print(Settings().get(args.get))
        return 0
    if args.check:
        from .doctor import run_checks
        return run_checks()

    if sys.platform == "win32":
        # Taskbar / Alt-Tab / notifications show Capricorn (with its icon), not "Python"
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationDisplayName(APP_NAME)
    from PyQt6.QtGui import QIcon
    ico = paths.ASSETS_DIR / ("icon.ico" if sys.platform == "win32" else "icon.png")
    qapp.setWindowIcon(QIcon(str(ico if ico.exists() else paths.ASSETS_DIR / "icon.png")))
    qapp.setQuitOnLastWindowClosed(False)

    if args.settings:
        theme.load_fonts()
        from .ui.settings_window import SettingsWindow
        from .brain.llm import LLM
        st = Settings()
        win = SettingsWindow(st, models=LLM(st).models)
        win.setWindowTitle("Capricorn - Settings  (restart Capri after saving: commands\\restart.bat)")
        win.show()
        qapp.setQuitOnLastWindowClosed(True)
        return qapp.exec()

    lock = QLockFile(str(paths.user_dir() / "capricorn.lock"))
    if not lock.tryLock(100):
        # Already running (e.g. the taskbar / Start icon was clicked): bring the running Capri up.
        from PyQt6.QtNetwork import QLocalSocket
        sock = QLocalSocket()
        sock.connectToServer(INSTANCE_KEY)
        if sock.waitForConnected(1500):
            sock.write(b"show\n")
            sock.waitForBytesWritten(1000)
            sock.disconnectFromServer()
        log.info("Capricorn is already running - asked it to show itself")
        return 0

    log.info("Capricorn %s starting (user dir: %s)", __version__, paths.user_dir())
    app = CapricornApp(qapp)
    app.start()
    from PyQt6.QtNetwork import QLocalServer
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    if server.listen(INSTANCE_KEY):
        def on_conn() -> None:
            c = server.nextPendingConnection()
            if c is not None:
                c.readyRead.connect(lambda c=c: (app.bring_up() if b"show" in bytes(c.readAll()) else None))
        server.newConnection.connect(on_conn)
    if sys.platform == "win32":
        threading.Thread(target=_start_menu_shortcut, daemon=True, name="shortcut").start()
    code = qapp.exec()
    lock.unlock()
    return code
