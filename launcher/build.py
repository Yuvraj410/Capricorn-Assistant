"""Rebuilds launcher/Capricorn.exe from launcher.c + launcher.rc (any OS, no Visual Studio needed):
    pip install ziglang
    python launcher/build.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
shutil.copyfile(here.parent / "assets" / "icon.ico", here / "icon.ico")
try:
    subprocess.run([sys.executable, "-m", "ziglang", "build-exe", "launcher.c", "launcher.rc",
                    "-target", "x86_64-windows-gnu", "-O", "ReleaseSmall", "-lc", "-lshell32", "-luser32",
                    "--subsystem", "windows", "-femit-bin=Capricorn.exe"], cwd=here, check=True)
finally:
    (here / "icon.ico").unlink(missing_ok=True)
    for junk in here.glob("Capricorn.pdb"):
        junk.unlink()
print("built", here / "Capricorn.exe")
