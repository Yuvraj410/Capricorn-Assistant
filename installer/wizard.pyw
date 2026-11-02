"""Capricorn Setup - a step-by-step installer window (started by Setup.exe).

Only uses the Python standard library (tkinter), because it runs *before* anything is installed.
Steps: Welcome -> Licence -> Location -> Brain (Ollama) -> Speech -> Voice -> Options -> Summary -> Install -> Done.
Nothing is downloaded or installed until you press Install on the summary page.

    pythonw installer\\wizard.pyw              # install
    pythonw installer\\wizard.pyw --uninstall  # remove (what Windows "Apps & features" runs)
"""
from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

SRC = Path(__file__).resolve().parents[1]                      # the folder Setup.exe is in
APP = "Capricorn"
WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Capricorn"


def _version() -> str:
    try:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (SRC / "capricorn" / "__init__.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "0.1.0"
    except OSError:
        return "0.1.0"


VERSION = _version()

# ---------------------------------------------------------------------------------- sizes (MB, on disk)
SIZE = {
    "core": 650,            # app + Python packages (PyQt6, numpy, faster-whisper, vosk ...)
    "wake": 70,             # Vosk wake-word model
    "gpu_speech": 1300,     # NVIDIA cuBLAS + cuDNN for faster-whisper on the GPU
    "voice_gpu": 12000,     # PyTorch (CUDA 12.8) + Chatterbox packages + voice model
    "voice_cpu": 6000,      # PyTorch (CPU) + Chatterbox packages + voice model
    "ollama_app": 1500,     # Ollama itself (only if we install it)
    "python": 110,          # Python 3.12, only when it had to be installed
}
WHISPER = [  # name, MB, label
    ("tiny.en", 75, "Tiny - fastest, makes the most mistakes"),
    ("base.en", 145, "Base - fast, decent"),
    ("small.en", 465, "Small - recommended: accurate and still quick"),
    ("medium.en", 1530, "Medium - most accurate, slow without a GPU"),
]
BRAINS = [  # model, MB, label, min RAM GB
    ("qwen3:4b", 2600, "Qwen3 4B - recommended: smart and quick", 8),
    ("qwen3:1.7b", 1400, "Qwen3 1.7B - light: for 8 GB RAM / older PCs", 4),
    ("qwen3:8b", 5200, "Qwen3 8B - smartest: needs 16 GB RAM or a good GPU", 16),
    ("llama3.2:3b", 2000, "Llama 3.2 3B - alternative, fast", 8),
]

# ---------------------------------------------------------------------------------- theme
BG, PANEL, FIELD = "#0D0A14", "#171020", "#211833"
TEXT, DIM = "#F4F1FA", "#B7A8C8"
PINK, CYAN, GREEN, PURPLE, YELLOW = "#FF0060", "#36DFFF", "#00F45B", "#7B3CFF", "#FFD23F"


def load_fonts() -> tuple[str, str]:
    """Use the app's own fonts (Rajdhani / Inter) for this window only - nothing is installed."""
    head, body = "Segoe UI Semibold", "Segoe UI"
    if WIN:
        try:
            for f in (SRC / "assets" / "fonts").glob("*.ttf"):
                ctypes.windll.gdi32.AddFontResourceExW(str(f), 0x10, 0)    # FR_PRIVATE
            head, body = "Rajdhani SemiBold", "Inter"
        except Exception:
            pass
    return head, body


# ---------------------------------------------------------------------------------- system checks
def mb(n: float) -> str:
    return f"{n / 1024:.1f} GB" if n >= 1024 else f"{int(n)} MB"


def ram_gb() -> float:
    if not WIN:
        try:
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
        except (ValueError, OSError, AttributeError):
            return 16.0

    class MEM(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = MEM()
    m.dwLength = ctypes.sizeof(MEM)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys / 2 ** 30


def nvidia_gpu() -> tuple[str, float] | None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW).stdout
        name, mem = out.strip().splitlines()[0].rsplit(",", 1)
        return name.strip(), float(mem) / 1024
    except Exception:
        return None


def ollama_exe() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(p) if p.exists() else None


def ollama_models(timeout: float = 2.0) -> list[str] | None:
    """Models pulled in a running Ollama, or None if Ollama isn't answering."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=timeout) as r:
            return [m.get("name", "") for m in json.load(r).get("models", [])]
    except Exception:
        return None


def free_mb(path: Path) -> float:
    p = path
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free / 2 ** 20
    except OSError:
        return 0.0


def default_target() -> Path:
    if WIN:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP
    return Path.home() / APP


# ---------------------------------------------------------------------------------- the window
class Wizard(tk.Tk):
    STEPS = ["Welcome", "Licence", "Location", "Brain", "Speech", "Voice", "Options", "Summary", "Install", "Done"]

    def __init__(self, uninstall: bool = False) -> None:
        super().__init__()
        self.head_font, self.body_font = load_fonts()
        self.title(f"{APP} Setup" if not uninstall else f"Uninstall {APP}")
        self.configure(bg=BG)
        self.geometry("940x640")
        self.minsize(880, 600)
        try:
            self.iconbitmap(str(SRC / "assets" / "icon.ico"))
        except Exception:
            pass
        self._style()
        self.ram = ram_gb()
        self.gpu = nvidia_gpu()
        self.ollama_path = ollama_exe()
        self.ollama_have = ollama_models() or []
        self.log_q: "queue.Queue[tuple]" = queue.Queue()
        self.cancelled = False
        self.proc: subprocess.Popen | None = None
        self.ok = False

        # choices
        self.v_accept = tk.BooleanVar(value=False)
        self.v_target = tk.StringVar(value=str(default_target()))
        # running Setup from an existing install (update / repair): keep using that folder
        self.v_portable = tk.BooleanVar(value=(SRC / "capricorn-data" / "python").exists())
        self.v_ollama = tk.StringVar(value="existing" if self.ollama_path else "install")
        rec_brain = "qwen3:4b" if self.ram >= 12 or self.gpu else "qwen3:1.7b"
        self.v_brain = tk.StringVar(value=rec_brain)
        self.v_whisper = tk.StringVar(value="small.en")
        self.v_gpu_speech = tk.BooleanVar(value=False)
        self.v_voice = tk.StringVar(value="sapi")
        self.v_voice_gpu = tk.BooleanVar(value=bool(self.gpu))
        bundled_ref = SRC / "reference-voices" / "capri.wav"
        self.v_ref = tk.StringVar(value=str(bundled_ref) if bundled_ref.is_file() else "")
        self.v_perms = tk.StringVar(value="safe")
        self.v_slang = tk.StringVar(value="Light")
        self.v_startup = tk.BooleanVar(value=True)
        self.v_desktop = tk.BooleanVar(value=True)
        self.v_startmenu = tk.BooleanVar(value=True)
        self.v_launch = tk.BooleanVar(value=True)

        self.v_voice_gpu.trace_add("write", lambda *_: self.after(10, lambda: self.page == 5 and self.show(5)))
        self._layout()
        if uninstall:
            self._uninstall_page()
        else:
            self.page = 0
            self.show(0)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._pump)

    # -- styling ----------------------------------------------------------------------------------
    def _style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        f = (self.body_font, 10)
        s.configure(".", background=BG, foreground=TEXT, font=f, fieldbackground=FIELD, bordercolor="#2c2140",
                    lightcolor=BG, darkcolor=BG, troughcolor=PANEL, focuscolor=CYAN)
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Panel.TLabel", background=PANEL)
        s.configure("Dim.TLabel", foreground=DIM)
        s.configure("PanelDim.TLabel", background=PANEL, foreground=DIM)
        s.configure("H1.TLabel", font=(self.head_font, 22, "bold"), foreground=CYAN)
        s.configure("H2.TLabel", font=(self.head_font, 13, "bold"), foreground=TEXT)
        s.configure("Size.TLabel", background=PANEL, foreground=GREEN, font=(self.body_font, 10, "bold"))
        s.configure("Warn.TLabel", foreground=YELLOW)
        s.configure("Err.TLabel", foreground=PINK)
        for w in ("TRadiobutton", "TCheckbutton"):
            s.configure(w, background=PANEL, foreground=TEXT, indicatorbackground=FIELD, indicatorforeground=CYAN,
                        padding=(2, 4))
            s.map(w, background=[("active", PANEL)], foreground=[("disabled", "#5d5070")],
                  indicatorbackground=[("selected", PINK), ("disabled", BG)])
        s.configure("Bg.TCheckbutton", background=BG)
        s.map("Bg.TCheckbutton", background=[("active", BG)])
        s.configure("TButton", background=PANEL, foreground=TEXT, borderwidth=2, padding=(16, 7),
                    font=(self.head_font, 11, "bold"))
        s.map("TButton", background=[("active", "#2a1030"), ("disabled", BG)], foreground=[("disabled", "#5d5070")],
              bordercolor=[("!disabled", PINK)])
        s.configure("Primary.TButton", bordercolor=GREEN)
        s.map("Primary.TButton", bordercolor=[("!disabled", GREEN)])
        s.configure("Link.TButton", background=PANEL, foreground=CYAN, borderwidth=0, padding=(0, 2),
                    font=(self.body_font, 10, "underline"))
        s.map("Link.TButton", background=[("active", PANEL)])
        s.configure("TEntry", fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT, padding=6)
        s.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT, arrowcolor=CYAN)
        s.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)],
              background=[("readonly", FIELD)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", "#2a1030")
        self.option_add("*TCombobox*Listbox.selectForeground", CYAN)
        s.configure("Horizontal.TProgressbar", background=CYAN, troughcolor=PANEL, bordercolor=PANEL, thickness=14)

    # -- frame layout -------------------------------------------------------------------------------
    def _layout(self) -> None:
        side = tk.Frame(self, bg=PANEL, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        try:
            img = tk.PhotoImage(file=str(SRC / "assets" / "icon.png"))
            k = max(1, img.width() // 96)
            self.logo = img.subsample(k, k)
            tk.Label(side, image=self.logo, bg=PANEL).pack(pady=(22, 4))
        except Exception:
            self.logo = None
        tk.Label(side, text="CAPRICORN", fg=PINK, bg=PANEL, font=(self.head_font, 20, "bold")).pack()
        tk.Label(side, text=f"SETUP  ///  v{VERSION}", fg=CYAN, bg=PANEL, font=(self.head_font, 11, "bold")).pack(pady=(0, 18))
        self.step_labels = []
        for name in self.STEPS:
            lab = tk.Label(side, text=f"  {name}", anchor="w", bg=PANEL, fg=DIM, font=(self.body_font, 11), padx=18)
            lab.pack(fill="x", ipady=4)
            self.step_labels.append(lab)
        tk.Label(side, text="free · local · open source", bg=PANEL, fg="#5d5070",
                 font=(self.body_font, 9)).pack(side="bottom", pady=12)

        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(main, bg=BG)
        self.content.pack(fill="both", expand=True, padx=28, pady=(22, 8))
        foot = tk.Frame(main, bg=BG)
        foot.pack(fill="x", padx=28, pady=(0, 18))
        self.status = ttk.Label(foot, text="", style="Dim.TLabel")
        self.status.pack(side="left")
        self.btn_cancel = ttk.Button(foot, text="CANCEL", command=self.on_close)
        self.btn_cancel.pack(side="right")
        self.btn_next = ttk.Button(foot, text="NEXT  >", style="Primary.TButton", command=self.next)
        self.btn_next.pack(side="right", padx=8)
        self.btn_back = ttk.Button(foot, text="<  BACK", command=self.back)
        self.btn_back.pack(side="right")

    def clear(self) -> None:
        self._live = None                       # page-specific live updater belongs to the old page
        for w in self.content.winfo_children():
            w.destroy()

    def header(self, title: str, sub: str = "") -> None:
        ttk.Label(self.content, text=title.upper(), style="H1.TLabel").pack(anchor="w")
        if sub:
            ttk.Label(self.content, text=sub, style="Dim.TLabel", wraplength=640, justify="left").pack(anchor="w", pady=(2, 12))

    def panel(self, parent=None, **pack) -> tk.Frame:
        f = tk.Frame(parent or self.content, bg=PANEL, highlightthickness=1, highlightbackground="#2c2140")
        f.pack(fill="x", pady=5, **pack)
        return f

    def option(self, parent, var, value, title, desc, size: float | None = None, state="normal", cmd=None):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=12, pady=3)
        rb = ttk.Radiobutton(row, text=title, variable=var, value=value, state=state, command=cmd or self.refresh)
        rb.grid(row=0, column=0, sticky="w")
        if size is not None:
            ttk.Label(row, text=mb(size) if size else "0 MB", style="Size.TLabel").grid(row=0, column=1, sticky="e")
        if desc:
            ttk.Label(row, text=desc, style="PanelDim.TLabel", wraplength=560, justify="left").grid(
                row=1, column=0, columnspan=2, sticky="w", padx=(26, 0))
        row.columnconfigure(0, weight=1)
        return rb

    def check(self, parent, var, title, desc="", size: float | None = None, state="normal"):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=12, pady=3)
        cb = ttk.Checkbutton(row, text=title, variable=var, state=state, command=self.refresh)
        cb.grid(row=0, column=0, sticky="w")
        if size is not None:
            ttk.Label(row, text=mb(size), style="Size.TLabel").grid(row=0, column=1, sticky="e")
        if desc:
            ttk.Label(row, text=desc, style="PanelDim.TLabel", wraplength=560, justify="left").grid(
                row=1, column=0, columnspan=2, sticky="w", padx=(26, 0))
        row.columnconfigure(0, weight=1)
        return cb

    def note(self, text: str, style: str = "Dim.TLabel", parent=None) -> ttk.Label:
        lab = ttk.Label(parent or self.content, text=text, style=style, wraplength=640, justify="left")
        lab.pack(anchor="w", pady=(6, 0))
        return lab

    # -- navigation ---------------------------------------------------------------------------------
    def show(self, i: int) -> None:
        self.page = i
        for k, lab in enumerate(self.step_labels):
            lab.configure(fg=CYAN if k == i else (TEXT if k < i else DIM),
                          bg="#2a1030" if k == i else PANEL,
                          font=(self.body_font, 11, "bold" if k == i else "normal"))
        self.clear()
        getattr(self, f"page_{self.STEPS[i].lower()}")()
        self.btn_back.configure(state="normal" if 0 < i < 8 else "disabled")
        self.btn_next.configure(text="INSTALL" if i == 7 else ("FINISH" if i == 9 else "NEXT  >"))
        self.btn_cancel.configure(state="disabled" if i == 9 else "normal")
        self.refresh()

    def next(self) -> None:
        if self.page == 9:
            self.finish()
            return
        if not self.validate():
            return
        if self.page == 7:
            self.show(8)
            self.start_install()
            return
        self.show(self.page + 1)

    def back(self) -> None:
        if self.page > 0:
            self.show(self.page - 1)

    def validate(self) -> bool:
        if self.page == 2:
            t = self.target()
            if t.exists() and any(t.iterdir()) and t != SRC and not (t / "capricorn").exists():
                if not messagebox.askyesno(APP, f"{t} isn't empty. Install into it anyway?"):
                    return False
        if self.page == 5 and self.v_voice.get() == "capri":
            ref = Path(self.v_ref.get())
            if not self.v_ref.get() or not ref.exists():
                messagebox.showinfo(APP, "Capri's own voice clones a recording you provide.\n\n"
                                         "Pick a clean 10-20 second clip of the voice (wav or mp3), "
                                         "or choose the Windows voice for now - you can add it later.")
                return False
        return True

    def refresh(self) -> None:
        """Enable / disable Next and update live labels."""
        ok = True
        if self.page == 1:
            ok = self.v_accept.get()
        if self.page == 7:
            ok = self.total_mb() < free_mb(self.target()) - 500
        if self.page == 8:
            ok = False
        self.btn_next.configure(state="normal" if ok else "disabled")
        upd = getattr(self, "_live", None)
        if upd:
            upd()

    def target(self) -> Path:
        return SRC if self.v_portable.get() else Path(self.v_target.get()).expanduser()

    def on_close(self) -> None:
        if self.page == 8 and not self.ok:
            if not messagebox.askyesno(APP, "Stop the installation?\n\nWhat's installed so far stays; "
                                            "run Setup again to finish later."):
                return
            self.cancelled = True
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
        elif self.page not in (8, 9) and not messagebox.askyesno(APP, "Exit Capricorn Setup?"):
            return
        self.destroy()

    # -- pages ----------------------------------------------------------------------------------------
    def page_welcome(self) -> None:
        self.header("Welcome, choom", "Capricorn puts Capri - a sarcastic little Night City netrunner - on your "
                    "desktop. Say \"Hey Capri\" and she opens apps, games, folders and websites, plays music, "
                    "looks things up, and chats back in her own voice. Everything runs on this PC: free, no "
                    "account, nothing sent to the cloud.")
        p = self.panel()
        ttk.Label(p, text="THIS PC", style="Size.TLabel").pack(anchor="w", padx=12, pady=(8, 2))
        rows = [
            ("Memory", f"{self.ram:.0f} GB RAM" + ("" if self.ram >= 8 else "  (8 GB+ recommended)")),
            ("Graphics", f"{self.gpu[0]} ({self.gpu[1]:.0f} GB)" if self.gpu else "No NVIDIA GPU found - everything still works on the CPU, a bit slower"),
            ("Ollama", "installed" + (f", {len(self.ollama_have)} model(s) downloaded" if self.ollama_have else "")
             if self.ollama_path else "not installed yet - Setup can install it for you"),
            ("Free space", f"{mb(free_mb(default_target()))} on the default drive"),
        ]
        for k, v in rows:
            r = tk.Frame(p, bg=PANEL)
            r.pack(fill="x", padx=12, pady=1)
            ttk.Label(r, text=k, style="PanelDim.TLabel", width=12).pack(side="left")
            ttk.Label(r, text=v, style="Panel.TLabel").pack(side="left")
        tk.Frame(p, bg=PANEL, height=8).pack()
        self.note("Next you'll pick what to install - each choice shows how much disk space it needs. "
                  "Nothing is downloaded until you press Install on the summary page.")

    def page_licence(self) -> None:
        self.header("Licence", "Capricorn is free and open source (MIT licence). The models it downloads have "
                    "their own free licences (Vosk: Apache 2.0, Whisper: MIT, Chatterbox: MIT, "
                    "Qwen3: Apache 2.0, Llama 3.2: Llama community licence).")
        box = tk.Text(self.content, height=14, bg=PANEL, fg=TEXT, relief="flat", wrap="word",
                      font=(self.body_font, 9), padx=12, pady=10, highlightthickness=1, highlightbackground="#2c2140")
        try:
            box.insert("1.0", (SRC / "LICENSE").read_text(encoding="utf-8"))
        except OSError:
            box.insert("1.0", "MIT License")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, pady=6)
        ttk.Checkbutton(self.content, text="I accept the licence", variable=self.v_accept, style="Bg.TCheckbutton",
                        command=self.refresh).pack(anchor="w", pady=4)

    def page_location(self) -> None:
        self.header("Install location", "Capricorn, its Python packages and its speech models all go into one "
                    "folder (Ollama and its AI model live in Ollama's own folder). No admin rights needed.")
        p = self.panel()
        r = tk.Frame(p, bg=PANEL)
        r.pack(fill="x", padx=12, pady=12)
        ent = ttk.Entry(r, textvariable=self.v_target, font=(self.body_font, 10))
        ent.pack(side="left", fill="x", expand=True)
        ttk.Button(r, text="BROWSE", command=self._browse).pack(side="left", padx=(8, 0))
        self.check(p, self.v_portable, f"Install right here instead (portable): {SRC}",
                   "Keeps everything in the folder you downloaded - handy for a USB stick or trying it out.")
        self.free_lab = self.note("")
        self._live = lambda: self.free_lab.configure(
            text=f"Free space there: {mb(free_mb(self.target()))}" + ("" if not self.v_portable.get()
                                                                      else "  (installing in place)"))
        ent.bind("<KeyRelease>", lambda e: self.refresh())

    def _browse(self) -> None:
        d = filedialog.askdirectory(initialdir=str(Path(self.v_target.get()).parent), title="Install Capricorn in...")
        if d:
            self.v_target.set(str(Path(d) / APP) if Path(d).name.lower() != APP.lower() else d)
            self.refresh()

    def page_brain(self) -> None:
        self.header("Capri's brain", "Chat and smart commands run on a free AI model through Ollama, on your own "
                    "PC. Simple commands (open apps, play music...) work even without it.")
        p = self.panel()
        if self.ollama_path:
            self.option(p, self.v_ollama, "existing", "Use my Ollama (already installed)", "", 0)
        else:
            self.option(p, self.v_ollama, "install", "Install Ollama for me (free, ~1 GB download)",
                        "Downloaded from ollama.com and installed just for you.", SIZE["ollama_app"])
            self.option(p, self.v_ollama, "existing", "I'll install Ollama myself",
                        "Get it from ollama.com - Setup downloads the model once Ollama is running.", 0)
        self.option(p, self.v_ollama, "skip", "Skip for now - commands only, no chat", "", 0)

        p2 = self.panel()
        ttk.Label(p2, text="AI MODEL", style="Size.TLabel").pack(anchor="w", padx=12, pady=(8, 0))
        self._brain_rbs = []
        for name, size, label, need in BRAINS:
            have = any(m == name or m.startswith(name + "-") for m in self.ollama_have)
            desc = "already downloaded" if have else ("" if self.ram >= need - 0.7 else f"needs about {need} GB RAM - you have {self.ram:.0f}")
            self._brain_rbs.append(self.option(p2, self.v_brain, name, label, desc, 0 if have else size))
        box = self.panel()
        tk.Label(box, text="NO ACCOUNT NEEDED", bg=PANEL, fg=YELLOW, font=(self.head_font, 11, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        ttk.Label(box, style="PanelDim.TLabel", wraplength=620, justify="left", text=(
            "When Ollama starts, its window may ask you to sign in or create an account. You don't need one - "
            "just close that window (or pick the local option). Capricorn only needs Ollama running quietly in "
            "the tray (llama icon) and everything stays on your PC.")).pack(anchor="w", padx=12, pady=(2, 10))

        def live() -> None:
            st = "disabled" if self.v_ollama.get() == "skip" else "normal"
            for rb in self._brain_rbs:
                rb.configure(state=st)
        self._live = live

    def page_speech(self) -> None:
        self.header("Hearing you", "\"Hey Capri\" is spotted by a tiny always-on model (70 MB, always installed). "
                    "Then Whisper writes down what you said - pick its size:")
        p = self.panel()
        for name, size, label in WHISPER:
            self.option(p, self.v_whisper, name, label, "", size)
        p2 = self.panel()
        if self.gpu:
            self.check(p2, self.v_gpu_speech, f"Use my NVIDIA GPU for speech ({self.gpu[0]})",
                       "Faster transcription. Adds NVIDIA's free CUDA libraries.", SIZE["gpu_speech"])
        else:
            self.check(p2, self.v_gpu_speech, "Use an NVIDIA GPU for speech", "No NVIDIA GPU found on this PC.",
                       SIZE["gpu_speech"], state="disabled")
        self.note("Small on the CPU answers in about a second on a modern PC.")

    def page_voice(self) -> None:
        self.header("Capri's voice", "How should Capri talk back? You can change this any time in Settings.")
        p = self.panel()
        self.option(p, self.v_voice, "none", "Text only", "Replies appear in chat bubbles, no sound.", 0)
        self.option(p, self.v_voice, "sapi", "Windows voice", "Built into Windows - instant, no download, but it "
                    "isn't Capri's voice.", 0)
        vsize = SIZE["voice_gpu"] if self.v_voice_gpu.get() else SIZE["voice_cpu"]
        self.option(p, self.v_voice, "capri", "Capri's own voice (local AI voice cloning)",
                    "Chatterbox Turbo (free, MIT) speaks in the voice of a short recording you provide. "
                    "Best with an NVIDIA GPU; works on the CPU but replies take a few seconds longer.", vsize,
                    cmd=lambda: self.show(5))
        if self.v_voice.get() == "capri":
            q = self.panel()
            gpu_txt = f"Use my NVIDIA GPU ({self.gpu[0]}) - fast" if self.gpu else "NVIDIA GPU (none found)"
            self.check(q, self.v_voice_gpu, gpu_txt, "Off = CPU-only PyTorch: smaller download, slower voice.",
                       None, state="normal" if self.gpu else "disabled")
            r = tk.Frame(q, bg=PANEL)
            r.pack(fill="x", padx=12, pady=(6, 4))
            ttk.Label(r, text="Voice recording:", style="Panel.TLabel").pack(side="left")
            ttk.Entry(r, textvariable=self.v_ref).pack(side="left", fill="x", expand=True, padx=8)
            ttk.Button(r, text="PICK FILE", command=self._pick_ref).pack(side="left")
            ttk.Label(q, style="PanelDim.TLabel", wraplength=620, justify="left", text=(
                "The included Capri recording is selected automatically when available. To change it, pick "
                "10-20 seconds of one person talking clearly, no music (wav, mp3, flac). Add mood clips later "
                "(see README).")).pack(anchor="w", padx=12, pady=(0, 10))

    def _pick_ref(self) -> None:
        f = filedialog.askopenfilename(title="Pick a voice recording",
                                       filetypes=[("Audio", "*.wav *.mp3 *.flac *.ogg *.m4a"), ("All files", "*.*")])
        if f:
            self.v_ref.set(f)

    def page_options(self) -> None:
        self.header("Options")
        p = self.panel()
        ttk.Label(p, text="WHAT MAY CAPRI OPEN?", style="Size.TLabel").pack(anchor="w", padx=12, pady=(8, 0))
        self.option(p, self.v_perms, "safe", "Safe (recommended)", "Websites and music freely; asks before "
                    "opening apps, files and folders (and remembers your yes).")
        self.option(p, self.v_perms, "full", "Full access", "Any app, game, folder, file or website without "
                    "asking. Shutdown / restart / sleep always ask first.")
        p2 = self.panel()
        r = tk.Frame(p2, bg=PANEL)
        r.pack(fill="x", padx=12, pady=10)
        ttk.Label(r, text="Night City slang:", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(r, textvariable=self.v_slang, values=["None", "Light", "Regular", "Heavy"], state="readonly",
                     width=12).pack(side="left", padx=8)
        ttk.Label(r, text="(more personality options in Settings)", style="PanelDim.TLabel").pack(side="left")
        p3 = self.panel()
        self.check(p3, self.v_startup, "Start Capricorn with Windows", "Runs quietly in the tray, ready for \"Hey Capri\".")
        self.check(p3, self.v_desktop, "Desktop shortcut")
        self.check(p3, self.v_startmenu, "Start menu shortcut", "Pin it to the taskbar from there.")

    def page_summary(self) -> None:
        self.header("Ready to install", "Here's what Setup will do. Press Install to start - it takes 5-30 "
                    "minutes depending on your choices and internet speed.")
        p = self.panel()
        for name, size in self.items():
            r = tk.Frame(p, bg=PANEL)
            r.pack(fill="x", padx=12, pady=2)
            ttk.Label(r, text=name, style="Panel.TLabel").pack(side="left")
            ttk.Label(r, text=mb(size) if size else "-", style="Size.TLabel").pack(side="right")
        tk.Frame(p, bg="#2c2140", height=1).pack(fill="x", padx=12, pady=6)
        r = tk.Frame(p, bg=PANEL)
        r.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(r, text="TOTAL DISK SPACE", bg=PANEL, fg=TEXT, font=(self.head_font, 12, "bold")).pack(side="left")
        tk.Label(r, text=mb(self.total_mb()), bg=PANEL, fg=CYAN, font=(self.head_font, 14, "bold")).pack(side="right")
        free = free_mb(self.target())
        if self.total_mb() >= free - 500:
            self.note(f"Not enough free space: {mb(free)} available on that drive. Go back and choose "
                      "smaller options or another location.", "Err.TLabel")
        else:
            self.note(f"Installing to {self.target()}   ·   free space there: {mb(free)}")

    def items(self) -> list[tuple[str, float]]:
        out = [("Capricorn app + Python packages", SIZE["core"]), ("Wake-word model (\"Hey Capri\")", SIZE["wake"])]
        w = next(x for x in WHISPER if x[0] == self.v_whisper.get())
        out.append((f"Speech recognition: Whisper {w[0]}", w[1]))
        if self.v_gpu_speech.get() and self.gpu:
            out.append(("NVIDIA libraries for GPU speech", SIZE["gpu_speech"]))
        if self.v_ollama.get() == "install":
            out.append(("Ollama (AI runtime)", SIZE["ollama_app"]))
        if self.v_ollama.get() != "skip":
            b = next(x for x in BRAINS if x[0] == self.v_brain.get())
            have = any(m == b[0] or m.startswith(b[0] + "-") for m in self.ollama_have)
            out.append((f"AI model: {b[0]}" + (" (already downloaded)" if have else ""), 0 if have else b[1]))
        v = self.v_voice.get()
        if v == "capri":
            gpu = self.v_voice_gpu.get() and self.gpu
            out.append((f"Capri's voice (PyTorch {'CUDA' if gpu else 'CPU'} + Chatterbox)",
                        SIZE["voice_gpu"] if gpu else SIZE["voice_cpu"]))
        else:
            out.append(("Voice: " + ("Windows voice" if v == "sapi" else "text only"), 0))
        out.append((f"Permissions: {'Safe' if self.v_perms.get() == 'safe' else 'Full access'}", 0))
        extras = [n for n, var in (("start with Windows", self.v_startup), ("desktop shortcut", self.v_desktop),
                                   ("Start menu", self.v_startmenu)) if var.get()]
        if extras:
            out.append(("Shortcuts: " + ", ".join(extras), 0))
        return out

    def total_mb(self) -> float:
        return sum(s for _, s in self.items())

    # -- install ------------------------------------------------------------------------------------------
    def page_install(self) -> None:
        self.header("Installing", "Grab a scop bar - this takes a while. You can keep using your PC.")
        self.step_lab = ttk.Label(self.content, text="Starting...", style="H2.TLabel")
        self.step_lab.pack(anchor="w", pady=(4, 6))
        self.bar = ttk.Progressbar(self.content, maximum=1000, style="Horizontal.TProgressbar")
        self.bar.pack(fill="x")
        self.sub_lab = ttk.Label(self.content, text="", style="Dim.TLabel")
        self.sub_lab.pack(anchor="w", pady=(4, 8))
        self.logbox = tk.Text(self.content, height=16, bg=PANEL, fg=DIM, relief="flat", wrap="none",
                              font=("Consolas", 9), padx=10, pady=8, highlightthickness=1,
                              highlightbackground="#2c2140")
        self.logbox.pack(fill="both", expand=True)

    def page_done(self) -> None:
        if self.ok:
            self.header("Capri's online", "Setup finished. Say \"Hey Capri\" (or \"Hey C\") and ask for something - "
                        "\"open YouTube\", \"play my liked music\", \"what's the weather in Tokyo?\". "
                        "Type instead with Ctrl+Alt+C.")
            p = self.panel()
            for t in ("Right-click the tray icon (or say \"open settings\") for every setting.",
                      "Commands and tips: the commands folder and README.md.",
                      "Pin Capricorn to the taskbar: Start menu > Capricorn > right-click > Pin to taskbar."):
                ttk.Label(p, text="•  " + t, style="Panel.TLabel", wraplength=620, justify="left").pack(anchor="w", padx=12, pady=3)
            tk.Frame(p, bg=PANEL, height=6).pack()
            ttk.Checkbutton(self.content, text="Start Capricorn now", variable=self.v_launch,
                            style="Bg.TCheckbutton").pack(anchor="w", pady=8)
            ttk.Button(self.content, text="OPEN README", command=lambda: os.startfile(str(self.target() / "README.md"))
                       if WIN else None).pack(anchor="w")
        else:
            self.header("Setup didn't finish", getattr(self, "fail_msg", "Something went wrong."))
            self.note(f"Full log: {self.logfile}" if hasattr(self, "logfile") else "")
            self.note("Fix the problem (usually the internet connection) and run Setup again - it continues "
                      "where it stopped.")
            self.v_launch.set(False)

    def finish(self) -> None:
        if self.ok and self.v_launch.get():
            exe = self.target() / "capricorn-data" / "python" / "Scripts" / "Capricorn.exe"
            if not exe.exists():
                exe = self.target() / "Capricorn.exe"
            try:
                subprocess.Popen([str(exe)], cwd=str(self.target())) if exe.exists() else \
                    subprocess.Popen(["cmd", "/c", str(self.target() / "Capricorn.bat")], creationflags=NO_WINDOW)
            except OSError:
                pass
        self.destroy()

    # logging from the worker thread
    def log(self, text: str) -> None:
        self.log_q.put(("log", text))

    def stage(self, title: str, sub: str = "") -> None:
        self.log_q.put(("stage", title, sub))
        self.log(f"== {title}")

    def progress(self, overall: float, sub: str | None = None) -> None:
        self.log_q.put(("bar", overall, sub))

    def _pump(self) -> None:
        try:
            while True:
                item = self.log_q.get_nowait()
                if item[0] == "log" and hasattr(self, "logbox") and self.logbox.winfo_exists():
                    self.logbox.insert("end", item[1].rstrip() + "\n")
                    self.logbox.see("end")
                    if int(self.logbox.index("end").split(".")[0]) > 3000:
                        self.logbox.delete("1.0", "500.0")
                elif item[0] == "stage" and hasattr(self, "step_lab") and self.step_lab.winfo_exists():
                    self.step_lab.configure(text=item[1])
                    self.sub_lab.configure(text=item[2])
                elif item[0] == "bar" and hasattr(self, "bar") and self.bar.winfo_exists():
                    self.bar["value"] = int(item[1] * 1000)
                    if item[2] is not None:
                        self.sub_lab.configure(text=item[2])
                elif item[0] == "done":
                    self.ok = item[1]
                    self.fail_msg = item[2]
                    self.show(9)
                elif item[0] == "call":
                    item[1]()
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def start_install(self) -> None:
        threading.Thread(target=Installer(self).run, daemon=True).start()

    # -- uninstall --------------------------------------------------------------------------------------
    def _uninstall_page(self) -> None:
        self.page = -1
        for lab in self.step_labels:
            lab.pack_forget()
        self.btn_back.pack_forget()
        self.v_keep = tk.BooleanVar(value=False)
        self.v_rm_model = tk.BooleanVar(value=False)
        self.header("Uninstall Capricorn", f"This removes Capricorn from {SRC}, its shortcuts and its "
                    "start-with-Windows entry.")
        p = self.panel()
        self.check(p, self.v_keep, "Keep my settings, voice clips and downloaded models",
                   "Leaves the capricorn-data folder in place (handy if you reinstall).")
        brain = ""
        try:
            import yaml  # noqa: F401  (not available here - parse the line instead)
        except ImportError:
            pass
        st = SRC / "capricorn-data" / "settings.yaml"
        if st.exists():
            m = re.search(r"^\s*model:\s*([\w.:\-]+)\s*$", st.read_text(encoding="utf-8", errors="ignore"), re.M)
            brain = m.group(1) if m and ":" in m.group(1) else ""
        self.brain_model = brain or "qwen3:4b"
        self.check(p, self.v_rm_model, f"Also delete the AI model from Ollama ({self.brain_model})",
                   "Ollama itself stays installed - remove it from Windows Settings > Apps if you don't need it.")
        self.btn_next.configure(text="UNINSTALL", command=self._do_uninstall)

    def _do_uninstall(self) -> None:
        self.btn_next.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        threading.Thread(target=self._uninstall_worker, daemon=True).start()

    def _uninstall_worker(self) -> None:
        msgs = []
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='Capricorn.exe'\" | "
              "Where-Object { $_.Name -eq 'Capricorn.exe' -or $_.CommandLine -like '*-m capri*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW)
        time.sleep(1)
        for folder in ("Startup", "Desktop", "Programs"):
            try:
                out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                      f"[Environment]::GetFolderPath('{folder}')"], capture_output=True, text=True,
                                     creationflags=NO_WINDOW).stdout.strip()
                for name in ("Capricorn.lnk", "Capricon.lnk"):
                    lnk = Path(out) / name
                    if lnk.exists():
                        lnk.unlink()
                        msgs.append(f"removed {lnk}")
            except Exception:
                pass
        if self.v_rm_model.get() and ollama_exe():
            subprocess.run([ollama_exe(), "rm", self.brain_model], creationflags=NO_WINDOW)
        if WIN:
            try:
                import winreg
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
            except OSError:
                pass
        keep = self.v_keep.get()
        # delete the folder after this window closes (the installer files are inside it)
        if WIN:
            if keep:
                cmd = (f'timeout /t 3 /nobreak >nul & for /d %d in ("{SRC}\\*") do @if /i not "%~nxd"=="capricorn-data" '
                       f'rmdir /s /q "%d" & del /q "{SRC}\\*.*"')
            else:
                cmd = f'timeout /t 3 /nobreak >nul & rmdir /s /q "{SRC}"'
            subprocess.Popen(["cmd", "/c", cmd], creationflags=NO_WINDOW | 0x00000008, cwd=os.environ.get("TEMP", "C:\\"))
        self.log_q.put(("call", lambda: (messagebox.showinfo(APP, "Capricorn has been removed. Later, choom."),
                                         self.destroy())))


# ---------------------------------------------------------------------------------- the actual install
class Installer:
    def __init__(self, wiz: Wizard) -> None:
        self.w = wiz
        self.t = wiz.target()
        self.data = self.t / "capricorn-data"
        self.vpy = self.data / "python" / ("Scripts/python.exe" if WIN else "bin/python")
        self.logf = None
        # weights for the overall bar
        self.steps: list[tuple[str, float, callable]] = []

    # helpers -----------------------------------------------------------------------------------------------
    def _write(self, line: str) -> None:
        self.w.log(line)
        if self.logf:
            try:
                self.logf.write(line.rstrip() + "\n")
                self.logf.flush()
            except OSError:
                pass

    def run(self) -> None:
        w = self.w
        plan = [("Copying Capricorn", 2, self.copy_files),
                ("Creating the Python environment", 3, self.make_venv),
                ("Installing Python packages", 25, self.pip_core)]
        if w.v_gpu_speech.get() and w.gpu:
            plan.append(("Installing NVIDIA libraries for GPU speech", 10, self.pip_gpu))
        plan += [("Applying your settings", 2, self.settings),
                 ("Downloading speech models", 12, self.models)]
        if w.v_ollama.get() == "install":
            plan.append(("Installing Ollama", 12, self.install_ollama))
        if w.v_ollama.get() != "skip":
            plan.append((f"Downloading the AI model ({w.v_brain.get()})", 18, self.pull_model))
        if w.v_voice.get() == "capri":
            plan.append(("Installing Capri's voice", 30, self.voice))
        plan += [("Shortcuts and finishing touches", 2, self.shortcuts), ("Checking everything", 2, self.check)]
        total = sum(p[1] for p in plan)
        done = 0.0
        try:
            self.data.mkdir(parents=True, exist_ok=True)
            (self.data / "logs").mkdir(exist_ok=True)
            w.logfile = self.data / "logs" / "setup.log"
            self.logf = open(w.logfile, "a", encoding="utf-8")
            self._write(f"Capricorn {VERSION} setup - {time.ctime()} - target {self.t}")
            for title, weight, fn in plan:
                if w.cancelled:
                    raise RuntimeError("Cancelled.")
                w.stage(title)
                base, span = done / total, weight / total
                self.frac = lambda f, sub=None, base=base, span=span: w.progress(base + span * max(0.0, min(1.0, f)), sub)
                self.frac(0)
                fn()
                done += weight
                w.progress(done / total)
            w.log_q.put(("done", True, ""))
        except Exception as e:
            self._write(f"FAILED: {e}")
            w.log_q.put(("done", False, f"{e}"))
        finally:
            if self.logf:
                self.logf.close()

    def sh(self, cmd: list[str], parse=None, cwd: Path | None = None, env_extra: dict | None = None,
           allow_fail: bool = False) -> int:
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PIP_DISABLE_PIP_VERSION_CHECK="1",
                   HF_HUB_DISABLE_SYMLINKS_WARNING="1", **(env_extra or {}))
        self._write("> " + " ".join(str(c) for c in cmd))
        self.w.proc = p = subprocess.Popen([str(c) for c in cmd], cwd=str(cwd or self.t), stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                           env=env, creationflags=NO_WINDOW, bufsize=1)
        for line in p.stdout:
            line = line.rstrip()
            if not line:
                continue
            if parse:
                try:
                    parse(line)
                except Exception:
                    pass
            if not re.search(r"\d+%\|", line) or line.endswith("100%"):   # don't flood the log with bars
                self._write(line)
        code = p.wait()
        if code != 0 and not allow_fail and not self.w.cancelled:
            raise RuntimeError(f"A step failed ({Path(str(cmd[0])).name} exit {code}). See the log for details.")
        return code

    def pct_parser(self, lo: float = 0.0, hi: float = 1.0):
        def parse(line: str) -> None:
            m = re.search(r"(\d{1,3})%", line)
            if m:
                self.frac(lo + (hi - lo) * int(m.group(1)) / 100, line[-90:])
        return parse

    def pip_parser(self, expected: int):
        seen = {"n": 0}

        def parse(line: str) -> None:
            if line.startswith(("Collecting", "Downloading", "Using cached", "Requirement already satisfied")):
                seen["n"] += 1
                self.frac(min(0.85, seen["n"] / expected), line[:90])
            elif line.startswith("Installing collected packages"):
                self.frac(0.9, "Installing packages...")
        return parse

    # steps --------------------------------------------------------------------------------------------------
    # what an installed Capricorn needs (the repo also has tests and the sources of the two exes)
    INSTALL_ITEMS = ["capricorn", "assets", "commands", "scripts", "tools", "installer", "launcher", "Setup.exe",
                     "README.md", "LICENSE", "requirements.txt", "requirements-voice.txt", "reference-voices"]
    SKIP = staticmethod(shutil.ignore_patterns("__pycache__", "*.pyc", "*.c", "*.rc", "*.manifest", "build.py", "*.pdb"))

    def copy_files(self) -> None:
        if self.t.resolve() != SRC.resolve():
            items = [SRC / n for n in self.INSTALL_ITEMS if (SRC / n).exists()]
            for i, item in enumerate(items):
                dst = self.t / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, ignore=self.SKIP, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst)
                self.frac((i + 1) / (len(items) + 1), item.name)
            self._write(f"Copied Capricorn to {self.t}")
        else:
            self._write("Installing in place.")
        # the files you start Capricorn with go in the top of the install folder
        for f in (SRC / "installer" / "files").glob("*"):
            shutil.copy2(f, self.t / f.name)
        exe = SRC / "launcher" / "Capricorn.exe"
        if exe.exists():
            try:
                shutil.copy2(exe, self.t / "Capricorn.exe")
            except OSError as e:                     # running from that very file (update in place)
                self._write(f"Capricorn.exe not replaced ({e})")
        self._write("Added Capricorn.exe and the start / update scripts.")

    def make_venv(self) -> None:
        if self.vpy.exists():
            self._write("Python environment already exists.")
            return
        py = Path(sys.executable)
        if py.name.lower() == "pythonw.exe":
            py = py.with_name("python.exe")
        self.sh([py, "-m", "venv", self.data / "python"])

    def pip_core(self) -> None:
        self.sh([self.vpy, "-m", "pip", "install", "--upgrade", "pip"], allow_fail=True)
        self.sh([self.vpy, "-m", "pip", "install", "-r", self.t / "requirements.txt"], parse=self.pip_parser(70))

    def pip_gpu(self) -> None:
        self.sh([self.vpy, "-m", "pip", "install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*"],
                parse=self.pip_parser(6))

    def settings(self) -> None:
        w = self.w
        self.sh([self.vpy, "-m", "capricorn", "--profile", w.v_perms.get()])
        sets = [f"stt.model={w.v_whisper.get()}",
                f"personality.slang={['None', 'Light', 'Regular', 'Heavy'].index(w.v_slang.get())}"]
        if w.v_gpu_speech.get() and w.gpu:
            sets += ["stt.device=cuda", "stt.compute_type=float16"]
        if w.v_ollama.get() != "skip":
            sets.append(f"brain.model={w.v_brain.get()}")
        if w.v_voice.get() in ("none", "sapi"):
            sets.append(f"voice.engine={w.v_voice.get()}")
        cmd = [self.vpy, "-m", "capricorn"]
        for s in sets:
            cmd += ["--set", s]
        self.sh(cmd)

    def models(self) -> None:
        self.sh([self.vpy, self.t / "scripts" / "download_models.py"], parse=self.pct_parser())

    def install_ollama(self) -> None:
        if ollama_exe():
            self._write("Ollama is already installed.")
            return
        tmp = Path(os.environ.get("TEMP", str(self.data))) / "OllamaSetup.exe"
        url = "https://ollama.com/download/OllamaSetup.exe"
        self._write(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                if self.w.cancelled:
                    raise RuntimeError("Cancelled.")
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    self.frac(0.8 * got / total, f"{mb(got / 2 ** 20)} of {mb(total / 2 ** 20)}")
        self.frac(0.85, "Running the Ollama installer (a window may flash up)...")
        self.sh([tmp, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], allow_fail=True)
        for _ in range(30):
            if ollama_exe():
                break
            time.sleep(1)
        if not ollama_exe():
            raise RuntimeError("Ollama didn't install. Get it from ollama.com, then run Setup again "
                               "(or choose 'Skip for now').")
        self._write("Ollama installed. If its window asks you to sign in, just close it - no account needed.")

    def _ensure_ollama_running(self) -> bool:
        if ollama_models() is not None:
            return True
        exe = ollama_exe()
        if not exe:
            return False
        self._write("Starting Ollama in the background...")
        subprocess.Popen([exe, "serve"], creationflags=NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            time.sleep(1)
            if ollama_models() is not None:
                return True
        return False

    def pull_model(self) -> None:
        model = self.w.v_brain.get()
        if not self._ensure_ollama_running():
            if self.w.v_ollama.get() == "existing":
                self._write("Ollama isn't running - skipped the model download. Start Ollama, then run:  "
                            f"ollama pull {model}")
                return
            raise RuntimeError("Ollama isn't answering. Start it from the Start menu and run Setup again.")
        have = ollama_models() or []
        if any(m == model or m.startswith(model + "-") for m in have):
            self._write(f"{model} is already downloaded.")
            return
        req = urllib.request.Request("http://127.0.0.1:11434/api/pull", data=json.dumps({"model": model}).encode(),
                                     headers={"Content-Type": "application/json"})
        last = ""
        with urllib.request.urlopen(req, timeout=60 * 60) as r:
            for raw in r:
                if self.w.cancelled:
                    raise RuntimeError("Cancelled.")
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if ev.get("error"):
                    raise RuntimeError(f"Ollama: {ev['error']}")
                st = ev.get("status", "")
                if ev.get("total"):
                    self.frac(ev.get("completed", 0) / ev["total"],
                              f"{st}: {mb(ev.get('completed', 0) / 2 ** 20)} of {mb(ev['total'] / 2 ** 20)}")
                if st != last:
                    self._write(st)
                    last = st
        self._write(f"{model} downloaded.")

    def voice(self) -> None:
        w = self.w
        cmd = [self.vpy, self.t / "scripts" / "install_voice.py", "--reference", w.v_ref.get(), "--no-play"]
        if not (w.v_voice_gpu.get() and w.gpu):
            cmd.append("--cpu")
        steps = {"Creating the voice": 0.03, "Updating pip": 0.05, "Installing PyTorch": 0.08,
                 "Installing the voice model": 0.6, "Installing Chatterbox": 0.7, "Downloading the voice": 0.75}

        def parse(line: str) -> None:
            for k, v in steps.items():
                if k in line:
                    self.frac(v, line.strip("[]. ")[:90])
            m = re.search(r"(\d{1,3})%", line)
            if m and "Downloading" in line:
                self.frac(0.75 + 0.2 * int(m.group(1)) / 100)
        self.sh(cmd, parse=parse)

    def shortcuts(self) -> None:
        w = self.w
        ps = self.t / "scripts"
        self.sh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps / "install_launcher.ps1"],
                allow_fail=True)
        for var, where in ((w.v_startup, "Startup"), (w.v_desktop, "Desktop"), (w.v_startmenu, "StartMenu")):
            if var.get():
                self.sh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps / "make_shortcut.ps1",
                         "-Where", where], allow_fail=True)
        if WIN:
            try:
                import winreg
                k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
                setup = self.t / "Setup.exe"
                vals = {"DisplayName": APP, "DisplayVersion": VERSION, "Publisher": "Capricorn contributors",
                        "InstallLocation": str(self.t), "DisplayIcon": str(self.t / "assets" / "icon.ico"),
                        "UninstallString": f'"{setup}" --uninstall', "URLInfoAbout": "https://github.com/"}
                for name, val in vals.items():
                    winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
                winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, int(self.w.total_mb() * 1024))
                winreg.CloseKey(k)
                self._write("Added to Windows Settings > Apps (for uninstalling).")
            except OSError as e:
                self._write(f"Couldn't register the uninstaller: {e}")

    def check(self) -> None:
        self.sh([self.vpy, "-m", "capricorn", "--check"], allow_fail=True)


def main() -> None:
    if WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Capricorn.Setup")
        except Exception:
            pass
    Wizard(uninstall="--uninstall" in sys.argv).mainloop()


if __name__ == "__main__":
    main()
