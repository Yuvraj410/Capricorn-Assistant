"""Rebuilds Setup.exe (repo root) from installer/setup.c + setup.rc (any OS, no Visual Studio):
    pip install ziglang
    python installer/build.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
shutil.copyfile(here.parent / "assets" / "icon.ico", here / "icon.ico")
try:
    subprocess.run([sys.executable, "-m", "ziglang", "build-exe", "setup.c", "setup.rc", "-target",
                    "x86_64-windows-gnu", "-O", "ReleaseSmall", "-lc", "-lshell32", "-luser32", "-lcomctl32",
                    "-lurlmon", "-ladvapi32", "-lgdi32", "--subsystem", "windows", "-femit-bin=Setup.exe"],
                   cwd=here, check=True)
    shutil.move(str(here / "Setup.exe"), str(here.parent / "Setup.exe"))
finally:
    (here / "icon.ico").unlink(missing_ok=True)
    for junk in here.glob("Setup.pdb"):
        junk.unlink()
print("built", here.parent / "Setup.exe")
