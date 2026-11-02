# CAPRICORN ///

**Capri** is a free, local, voice-activated desktop assistant for Windows, with a cyberpunk attitude.

Say **"Hey Capri"** and she pops up over whatever you're doing, answers in neon chat bubbles (and out loud, in her own voice if you want), and gets things done: she opens apps, games, folders, files and websites, plays and controls your music, looks things up on the web, and chats with you using an AI model that runs on your own PC.

- **100% free.** No subscriptions, no API keys, no account.
- **Private.** Speech recognition, the AI brain and the voice all run on your PC. Nothing you say is sent to a cloud service. Internet is only used for websites, web lookups you ask for, and the one-time downloads during setup.
- **Light when idle.** Only a tiny wake-word recogniser runs all the time (about 1–3% CPU). The big models load when needed.
- **Safe by design.** Capri can only do a fixed list of things (open, play, close, look up...), and a permissions file you control decides what she may open.

> Capricorn is a fan-made project inspired by Cyberpunk 2077. It is not affiliated with or endorsed by CD PROJEKT RED.

---

## Contents

1. [What Capri can do](#what-capri-can-do)
2. [Requirements](#requirements)
3. [Installing (Setup.exe)](#installing-setupexe)
4. [Disk space](#disk-space)
5. [Ollama: no account needed](#ollama-no-account-needed)
6. [Talking to Capri](#talking-to-capri)
7. [Her voice](#her-voice)
8. [Settings](#settings)
9. [Permissions and privacy](#permissions-and-privacy)
10. [Troubleshooting](#troubleshooting)
11. [Updating and uninstalling](#updating-and-uninstalling)
12. [For developers](#for-developers)
13. [Credits and licences](#credits-and-licences)

---

## What Capri can do

| | |
|---|---|
| **Wake up** | "Hey Capri", "Hey Capricorn", "Capri", or the short form "Hey C". Wake word and command in one breath works too: "Capri, play lofi beats", "C, pause". |
| **Have a conversation** | After she answers she keeps listening for a few seconds, so you can just reply ("yes", "what about tomorrow?") without saying her name again. |
| **Apps and games** | "Open Discord", "Play Skyrim", "Launch Cyberpunk on Steam". She knows your Steam library and everything in your Start menu. Steam games open on their library page and launch; games you don't have installed open in Steam with a reminder. |
| **Folders and files** | "Open my downloads", "Open the resume pdf", "Open my projects folder" (your own folder names, set in Settings). |
| **Look things up** | "Look up the stock market", "Who won the game last night?", "What's the latest on GTA 6?". She searches the web, reads the results and tells you the answer, with sources in the chat. "Google best ramen" opens a results page instead. |
| **Music** | "Play Shelter by Porter Robinson", "Play my liked music", "Play the top 10 songs", "Play lofi beats" (YouTube Music, free, no account). "Pause", "Next song", "Volume up", "What's playing?" work with YouTube Music, Spotify, the Opera GX sidebar player and browsers. |
| **Close things** | "Close the game", "Stop Elden Ring", "Quit Discord", "Close the YouTube tab". |
| **Knows what's going on** | She can see what's playing, which app you're looking at and which game is running, so "pause this song" or "close this game" just work. |
| **System** | "Lock the PC". Sleep, restart and shutdown always ask first. |
| **Chat** | Anything else goes to the local AI in Capri's cheeky Night City persona. How much slang and sass she uses is up to you. |
| **Typed chat** | Press `Ctrl+Alt+C` or click Capri to type instead of talking. |
| **Looks** | Her expression follows what she says (smile, laughing, surprised, sad, angry, thinking); she blinks, talks, glitches in, and **dances while music plays**. "Minimal mode" shrinks her to an animated visor face. |
| **Plays nice** | While she listens and talks, other apps (music, videos, games) turn down automatically, like a phone assistant, then come back. |

The full list of voice commands and the helper scripts is in **[`commands/README.md`](commands/README.md)**.

---

## Requirements

| | Minimum | Recommended |
|---|---|---|
| Windows | 10 or 11, 64-bit | 11 |
| Memory | 8 GB RAM | 16 GB RAM |
| Disk | about 2 GB (no AI brain, Windows voice) | 5–20 GB depending on your choices ([table below](#disk-space)) |
| Graphics | none needed, everything runs on the CPU | an NVIDIA GPU makes speech, the AI and her voice faster |
| Other | a microphone; internet during setup | speakers or headphones for her voice |

No admin rights are needed. Python 3.12 is installed for your user account if you don't have it (Setup asks first).

---

## Installing (Setup.exe)

1. **Download** this repository (green **Code** button > **Download ZIP**, or a release zip) and **extract the whole zip** (right-click > *Extract All*). Setup can't run from inside the zip.
2. **Double-click `Setup.exe`.**
   - If Python 3.12 isn't installed, Setup offers to download it from python.org (about 26 MB) and installs it just for you. Your other programs aren't affected.
   - Windows SmartScreen may warn about an unrecognised app, because the exe isn't code-signed. Click *More info* > *Run anyway*. The source of both exes is in this repo (`installer/setup.c`, `launcher/launcher.c`).
3. **Follow the steps.** Nothing is downloaded or installed until you press **Install** on the summary page:

| Step | What you choose |
|---|---|
| **Welcome** | Shows what Setup found on your PC: RAM, NVIDIA GPU, Ollama, free space. |
| **Licence** | The MIT licence. |
| **Location** | Where Capricorn goes (default `%LOCALAPPDATA%\Programs\Capricorn`), or *install right here* (portable). |
| **Brain** | Install Ollama for you, use your existing Ollama, or skip AI chat for now. Then pick the AI model; Setup recommends one for your RAM. |
| **Speech** | Whisper model size (tiny / base / small / medium) and optional NVIDIA GPU acceleration. |
| **Voice** | Text only, the Windows voice, or Capri's own voice (local voice cloning) with your recording. |
| **Options** | Safe or full-access permissions, how much slang, start with Windows, desktop and Start menu shortcuts. |
| **Summary** | Everything you chose with its disk space, the total, and the free space on that drive. Install is greyed out if it won't fit. |
| **Install** | Progress bar and a live log. Usually 5–30 minutes depending on your choices and internet speed. |
| **Done** | Start Capricorn, open this README. |

Setup also adds Capricorn to **Windows Settings > Apps** so you can uninstall it like any other program. The install log is saved to `capricorn-data\logs\setup.log`.

To start Capricorn later: Start menu > **Capricorn**, the desktop shortcut, or `Capricorn.exe` in the install folder. To **pin it to the taskbar**: Start menu > Capricorn > right-click > *Pin to taskbar*. Clicking it while Capri is running opens the chat.

---

## Disk space

Everything except Ollama goes into one folder (the install folder and its `capricorn-data` subfolder).

| Part | Disk space | Notes |
|---|---|---|
| Capricorn + Python packages | ~650 MB | always |
| Wake-word model (Vosk) | ~70 MB | always |
| Speech recognition (Whisper) | tiny 75 MB · base 145 MB · **small 465 MB** · medium 1.5 GB | small is recommended |
| GPU speech (NVIDIA CUDA libraries) | ~1.3 GB | optional, NVIDIA only |
| Ollama (AI runtime) | ~1.5 GB | only if Setup installs it; lives in Ollama's own folder |
| AI model | qwen3:1.7b 1.4 GB · **qwen3:4b 2.6 GB** · llama3.2:3b 2.0 GB · qwen3:8b 5.2 GB | stored by Ollama |
| Capri's own voice | ~12 GB with NVIDIA GPU · ~6 GB CPU-only | optional: PyTorch + Chatterbox + the voice model |
| Windows voice / text only | 0 MB | |
| Python 3.12 | ~110 MB | only if it wasn't installed |

Typical totals: **about 2 GB** (Windows voice, no AI chat), **about 5.5 GB** (recommended: small speech model, Ollama + qwen3:4b, Windows voice), **about 17 GB** (everything, with Capri's voice on an NVIDIA GPU).

---

## Ollama: no account needed

Capri's brain runs through **[Ollama](https://ollama.com)**, a free program that runs AI models on your own PC.

- Setup can install it for you, or you can install it yourself from [ollama.com/download](https://ollama.com/download).
- **When Ollama starts, its window may ask you to sign in or create an account. You don't need one.** Close that window, or choose the local option. Capricorn only needs Ollama running quietly in the tray (the llama icon), and everything stays on your PC.
- Setup downloads the AI model for you. To switch models later: Settings > Brain, or `commands\change-brain.bat`. Manually: `ollama pull qwen3:8b`, then pick it in Settings.
- Without Ollama, simple commands (open, play, pause, close...) still work. Only free-form chat and web answers need the brain.

---

## Talking to Capri

- **"Hey Capri"** wakes her (also "Hey Capricorn", "Capri", "Hey C"). Wake word and command together works too: "Capri, open YouTube".
- **Just reply** after she answers. She keeps listening for about 5 seconds (8 after a question) and the bubble shows *"● listening - just answer"*. Saying nothing, "thanks" or "that's all" ends the conversation.
- **Confirmations:** when something needs your OK, say **yes** or **no** (or click the buttons). A yes is remembered, so she won't ask again for that same app, folder or site. Sleep, restart and shutdown always ask.
- **Thinking pauses are fine.** "Uh..." or "um" doesn't count as your command; she waits for the rest.
- **Type instead:** `Ctrl+Alt+C` or click Capri.
- **Tray icon:** chat, settings, mute microphone, minimal mode, restart, quit.
- **Move her** by dragging. "Minimal mode" / "normal mode" switches her look. "Speak louder" / "talk quieter" changes her voice volume.

---

## Her voice

Choose in Setup or later in Settings > Voice:

| Option | |
|---|---|
| **Text only** | Chat bubbles, no sound. |
| **Windows voice** | Instant and built in, but not Capri's voice. |
| **Capri's own voice** | [Chatterbox Turbo](https://github.com/resemble-ai/chatterbox) (free, MIT licence) runs locally and **clones the voice of a short recording you provide**. |

**No voice ships with Capricorn.** Bring a clean 10–20 second recording (one person, no music) of a voice you have the right to use. Setup copies it to `capricorn-data\voices\capri.wav`. You can also install the voice later with `commands\install-capri-voice.bat`.

Extras, all optional:
- **Mood clips:** add `capri-happy.wav`, `capri-playful.wav`, `capri-sad.wav`, `capri-surprised.wav`, `capri-angry.wav` and `capri-calm.wav` (about 12–15 s each) next to `capri.wav`, and she speaks every reply in the matching mood.
- **Recorded lines:** exact recordings of her fixed lines play instead of the cloned voice (`tools\split_voice_lines.py`, see `commands\README.md`).
- **Pronunciation:** add your own spellings in Settings > Voice > Pronunciations (e.g. `gonk: gonnk`). Times, dates, numbers and money ("9:51 PM", "$4.99", "RTX 5070") are read naturally.
- **Try it:** Settings > Voice > *Test her voice*, or `commands\test-voice.bat`.

Her voice is about 5× faster on an NVIDIA GPU. On a CPU, replies take a few seconds longer to start.

Please only clone voices you have the right to use, and don't publish clips of someone else's voice.

---

## Settings

Open **Settings** from the tray icon, the SETTINGS button in the chat window, `commands\settings.bat`, or by saying "open settings". Every setting is there, grouped and searchable, with an explanation:

- **Personality:** how much Night City slang and Gen Z slang, how sassy, reply length.
- **Conversation:** how long she keeps listening after replies.
- **Voice:** engine, volume, pronunciations, mood, ducking of other apps, plus a test box.
- **Wake word and listening:** wake words, sensitivity, how long a pause ends your command, microphone.
- **Speech recognition, Brain, Look and screen, Music, Shortcuts, Sounds.**

Changes apply as soon as you press Save. No restart needed; a voice or speech model change reloads in the background.

Your personal files are in `capricorn-data\` (tray > *Open settings folder*). It is never uploaded:

| File | |
|---|---|
| `settings.yaml` | everything from the Settings screen |
| `permissions.yaml` | what Capri may open |
| `approvals.json` | things you already said yes to |
| `voices\` | your voice recording(s) |
| `logs\capricorn.log` · `logs\actions.log` · `logs\setup.log` | what she heard, every action she took, the install log |

---

## Permissions and privacy

Each category (`apps`, `folders`, `files`, `web`, `media_control`, `system`) has a mode: `all` · `allowlist` · `ask` · `off`. Setup offers two profiles:

- **Safe** (default): websites and music freely; asks before opening apps, files and folders, and remembers your yes.
- **Full access:** opens anything without asking (power actions still ask).

Switch later with `commands\permissions-safe.bat` / `permissions-full.bat`, or edit `permissions.yaml`.

Hard rules that no setting can change:
- No shell commands or scripts. Only the named actions in `capricorn/actions/registry.py` exist.
- Executables and scripts are never "opened as files"; programs launch only through Start menu entries or shortcuts.
- Sleep, restart and shutdown always ask.

What leaves your PC: web pages you open, web searches you ask for (sent to DuckDuckGo), YouTube Music lookups for songs, and the downloads during setup and updates. Your voice, your commands and the AI conversation stay local.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Setup says files are missing | You ran it from inside the zip. Extract the zip first. |
| SmartScreen blocks Setup.exe | *More info* > *Run anyway* (the exe isn't code-signed; source is in `installer/`). |
| Setup failed during install | Check your internet and run Setup again; it continues where it stopped. The log is in `capricorn-data\logs\setup.log`. |
| Capri never wakes | Windows Settings > Privacy > Microphone must allow desktop apps. Check the right microphone in Settings > Wake word. Run `Capricorn-debug.bat` to see what she hears. |
| She wakes by accident | Raise *Wake sensitivity* in Settings, or remove the short "C" wake word. |
| "Brain offline" | Start Ollama (Start menu > Ollama; it lives in the tray). If the model is missing: `ollama pull qwen3:4b`. |
| She cuts you off mid-sentence | Raise *Pause that ends a command* in Settings > Wake word. |
| No voice | Settings > Voice > engine. For Capri's voice, the first start takes about 25 s to load; see `capricorn-data\logs\voice.log`. |
| Voice too quiet or loud | "Speak louder" / "talk quieter", or Settings > Voice > volume. |
| Hotkey does nothing | Another app uses Ctrl+Alt+C. Change it in Settings > Look. |
| Capri hidden by a game | Use borderless-windowed mode; exclusive fullscreen hides overlays. |
| Something else | Tray > Restart Capricorn. Logs are in `capricorn-data\logs\`. |

---

## Updating and uninstalling

**Update:** download the new version, extract it and run its `Setup.exe` with the same install folder, or choose *install right here* in your existing folder. Your settings, voice and models are kept. If you installed into a git clone: `git pull`, then run `update.bat` in that folder.

**Uninstall:** Windows Settings > Apps > **Capricorn** > Uninstall. You can keep or remove your settings and models. Ollama is a separate program; remove it from the same Apps list if you don't need it.

---

## For developers

```
Setup.exe              the installer (source: installer/setup.c) - the only thing users run
installer/
  wizard.pyw           the setup wizard window (Python standard library + tkinter)
  files/               Capricorn.bat, update.bat ... - Setup puts these in the install folder
launcher/
  Capricorn.exe        prebuilt launcher (source: launcher.c) - Setup puts it in the install folder
capricorn/
  app.py               Qt app: tray, overlay, chat, settings window, wiring
  audio/               wake-word listener (Vosk), speech-to-text (faster-whisper), ducking
  brain/               rules (instant commands), Ollama client, router
  actions/             everything Capri can do: web, research, apps, files, media, system
  security/            permission checks
  tts/                 voice: text prep / number reading, Chatterbox worker (runs in voice-env), Windows voice
  ui/                  theme, neon bubbles, sprite animations, chat window, settings window
  system_context.py    what's playing / focused / running, for the AI
  defaults/            default settings + permission profiles
assets/                character art, fonts, sounds, icon
commands/              double-click helper scripts + full command reference
scripts/, tools/       model downloads, voice installer, shortcuts, voice-line splitter
tests/                 pytest suite (runs on any OS)
```

An installed Capricorn folder looks like this (the repo minus tests and exe sources, plus):

```
Capricorn.exe, Capricorn.bat     start Capri
Capricorn-debug.bat              start with a console (see what she hears)
update.bat, install_startup.bat, remove_startup.bat
capricorn-data\                  Python environments, models, logs, your settings (never uploaded)
```

- **Run from source:** clone the repo and run `Setup.exe` with *install right here*. It sets everything up inside the clone; the files it adds are git-ignored. Or by hand: `py -3.12 -m venv capricorn-data\python`, then `capricorn-data\python\Scripts\pip install -r requirements.txt` and `capricorn-data\python\Scripts\python scripts\download_models.py`, then `capricorn-data\python\Scripts\python -m capricorn`.
- **Tests:** `pip install pytest`, then `python -m pytest -q` (or `commands\run-tests.bat`).
- **Rebuild the exes** (any OS, no Visual Studio): `pip install ziglang`, then `python installer/build.py` and `python launcher/build.py`.
- `capricorn-data\` is git-ignored: it holds the Python environments, models, logs and personal settings.

---

## Credits and licences

- **Code:** MIT (see `LICENSE`).
- **Character art and icon** (`assets/character`, `assets/icon.*`): © the Capricorn author, included for use with this project.
- **Fonts:** [Rajdhani](https://fonts.google.com/specimen/Rajdhani) and [Inter](https://rsms.me/inter/), SIL Open Font License (`assets/fonts`).
- **Built on:**
  - [Vosk](https://alphacephei.com/vosk/) (Apache-2.0)
  - [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT)
  - [Ollama](https://ollama.com) (MIT)
  - [Chatterbox](https://github.com/resemble-ai/chatterbox) (MIT)
  - [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) (GPL v3)
  - [ddgs](https://github.com/deedy5/ddgs) (MIT)
  - [ytmusicapi](https://github.com/sigma67/ytmusicapi) (MIT)
  - [pycaw](https://github.com/AndreMiras/pycaw) (MIT)
  - [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) (MIT)
  - [Zig](https://ziglang.org) (to build the exes)
- **AI models** are downloaded at install time under their own licences:
  - Qwen3 (Apache-2.0)
  - Llama 3.2 (Llama Community License)
  - Whisper (MIT)
  - Chatterbox (MIT)
- **Slang and vibe** inspired by Cyberpunk 2077. Fan project, not affiliated with CD PROJEKT RED.
