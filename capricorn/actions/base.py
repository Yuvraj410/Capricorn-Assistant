"""Shared types for actions."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .. import paths

_action_log = logging.getLogger("capricorn.actions")


@dataclass
class Result:
    ok: bool = True
    say: str = ""
    emotion: str = "smile"
    # When set, the UI asks the user; on "yes" it calls confirm_run() and shows its Result.
    confirm_question: Optional[str] = None
    confirm_run: Optional[Callable[[], "Result"]] = None
    approve: Optional[tuple[str, str]] = None      # (category, key) remembered when the user says yes
    data: dict = field(default_factory=dict)


def log_action(name: str, target: str, verdict: str) -> None:
    """Append to capricorn-data/logs/actions.log - a record of everything Capri did."""
    try:
        with open(paths.logs_dir() / "actions.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{name}\t{verdict}\t{target}\n")
    except OSError:
        _action_log.exception("could not write actions.log")
