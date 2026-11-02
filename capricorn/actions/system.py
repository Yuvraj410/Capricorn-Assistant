"""Lock / sleep / shutdown / restart, and the clock. Power actions always need confirmation."""
from __future__ import annotations

import ctypes
import datetime as _dt
import logging
import subprocess
import sys

from .. import persona
from ..security.permissions import ASK, DENY, Permissions
from .base import Result, log_action

log = logging.getLogger(__name__)
CREATE_NO_WINDOW = 0x08000000


def _do(op: str) -> None:
    if sys.platform != "win32":
        log.info("system op %s (no-op on this OS)", op)
        return
    if op == "lock":
        ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
    elif op == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=CREATE_NO_WINDOW)
    elif op == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "5"], creationflags=CREATE_NO_WINDOW)
    elif op == "restart":
        subprocess.Popen(["shutdown", "/r", "/t", "5"], creationflags=CREATE_NO_WINDOW)


def system(op: str, perms: Permissions) -> Result:
    op = (op or "").lower().strip()
    op = {"reboot": "restart", "power off": "shutdown", "turn off": "shutdown", "lock screen": "lock"}.get(op, op)
    if op not in {"lock", "sleep", "shutdown", "restart"}:
        return Result(False, *persona.line("not_understood"))
    d = perms.check_system(op)
    if d.verdict == DENY:
        log_action("system", op, "denied")
        return Result(False, *persona.line("denied", reason=d.reason))

    def run() -> Result:
        try:
            _do(op)
            log_action("system", op, "ok")
            return Result(True, *persona.line(op))
        except Exception:
            log.exception("system op failed")
            return Result(False, *persona.line("error"))

    if d.verdict == ASK:
        q = {"lock": "Lock the PC?", "sleep": "Put the PC to sleep?",
             "shutdown": "Shut down the PC?", "restart": "Restart the PC?"}[op]
        return Result(True, "", "surprised", confirm_question=q, confirm_run=run, approve=(d.category, d.key))
    return run()


def tell_time() -> Result:
    now = _dt.datetime.now()
    t = now.strftime("%I:%M %p").lstrip("0")
    date = now.strftime("%A, %B ") + str(now.day)
    return Result(True, *persona.line("time", time=t, date=date))
