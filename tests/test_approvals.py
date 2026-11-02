"""A 'yes' is remembered (per app / folder / file / site); power actions always ask."""
import shutil
from pathlib import Path

from capricorn import paths
from capricorn.security.permissions import ALLOW, ASK, Permissions


def perms_in(tmp: Path, profile="safe") -> Permissions:
    f = tmp / "permissions.yaml"
    shutil.copyfile(paths.DEFAULTS_DIR / f"permissions.{profile}.yaml", f)
    return Permissions(f)


def test_yes_is_remembered_and_persists(tmp_path):
    p = perms_in(tmp_path)
    d = p.check_app("Steam")
    assert d.verdict == ASK and (d.category, d.key) == ("apps", "steam")
    assert p.remember(d.category, d.key)
    assert p.check_app("Steam").verdict == ALLOW
    assert p.check_app("Discord").verdict == ASK            # only that app
    assert Permissions(tmp_path / "permissions.yaml").check_app("Steam").verdict == ALLOW   # survives restart


def test_files_and_sites_remembered(tmp_path):
    p = perms_in(tmp_path)
    f = Path.home() / "Downloads" / "notes.txt"
    d = p.check_file(f)
    assert d.verdict == ASK
    p.remember(d.category, d.key)
    assert p.check_file(f).verdict == ALLOW
    assert p.check_file(Path.home() / "Downloads" / "other.txt").verdict == ASK


def test_power_actions_always_ask(tmp_path):
    p = perms_in(tmp_path, "full")
    d = p.check_system("shutdown")
    assert d.verdict == ASK
    assert not p.remember(d.category, d.key)
    assert p.check_system("shutdown").verdict == ASK


def test_forget(tmp_path):
    p = perms_in(tmp_path)
    p.remember("apps", "steam")
    p.forget_approvals()
    assert p.check_app("Steam").verdict == ASK
    assert not (tmp_path / "approvals.json").exists()


def test_action_result_carries_approval(tmp_path, monkeypatch):
    from capricorn.actions import apps
    from capricorn.actions.apps import AppEntry, AppIndex
    p = perms_in(tmp_path)
    idx = AppIndex(); idx.entries = [AppEntry("Steam", "steam.exe", "appid")]; idx._last = 9e18
    launched = []
    monkeypatch.setattr(apps, "_launch", lambda e: launched.append(e.name))
    r = apps.open_app("steam", idx, p)
    assert r.confirm_question and r.approve == ("apps", "steam")
    p.remember(*r.approve)
    r2 = apps.open_app("steam", idx, p)
    assert r2.confirm_question is None and launched == ["Steam"]
