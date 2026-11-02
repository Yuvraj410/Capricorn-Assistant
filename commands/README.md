# Capricorn commands

Two kinds of commands:
1. **Things you say to Capri**: voice ("Hey Capri, ...") or typed in the chat window (`Ctrl+Alt+C`).
2. **Helper scripts** in this folder: double-click them to manage Capricorn.

---

## 1. Things you can say

Start with the wake word: **"Hey Capri"**, **"Hey Capricorn"**, **"Capri"**, **"Capricorn"**, **"Hey C"** or just **"C"**.
Short "C" works as "Hey C ..." or as the first word followed by a command ("C, open YouTube", "C, pause"), so everyday "I see" / "see you" doesn't wake her (turn it off with `wake.short_words: []`).
Say the command in the same breath ("Capri, open YouTube") or wait for *Listening...* and then say it.
In the chat window, just type the command without the wake word.

Wording is flexible: "please", "can you", "for me" and so on are ignored.
You can pause mid-sentence ("play... my liked music"): Capri waits for about 1.2 s of quiet before she acts (`wake.end_silence`).
If she only caught half of it ("play my-"), she asks you to repeat instead of guessing.
Anything Capri doesn't recognise below goes to her AI brain, which can still pick the right action ("I need something chill to study to" → plays lo-fi).

### Apps & games
| Say | What happens |
|---|---|
| "Open Discord" · "Launch Spotify" · "Start Notepad" | Launches the app (anything in your Start Menu or a desktop shortcut) |
| "Play Skyrim" · "Play Cyberpunk" · "Play GTA" | Launches the game if it's installed (Steam library + shortcuts; abbreviations like GTA, RDR2, CS2 work). Otherwise treated as a song. Every word you say must be in the game's name, so "God of War" never opens a different game |
| "Play Hollow Knight on Steam" · "Launch the game Elden Ring" | Always a game |
| "Open Steam" | Opens Steam itself |
| "Launch Elden Ring" (not installed) | Finds it on Steam and opens its page in Steam: your **library page** if you own it (with the Install button), otherwise the **store page**. Capri tells you to install it first |

When you launch an installed Steam game, Capri brings **Steam to the front on the game's library page**, then launches it, so you can see what's happening even if you were in your browser.

### Closing games & apps
| Say | What happens |
|---|---|
| "Close the game" · "Quit game" · "Kill the game" | Closes the Steam game that's running |
| "Close Black Myth Wukong" · "Stop Elden Ring" · "Quit Cyberpunk" | Closes that game |
| "Close Discord" · "Quit Spotify" · "Exit Steam" | Closes that app's windows (it may ask you to save) |
| "Close this tab" · "Close the tab" | Closes the tab you're looking at in your browser (Ctrl+W) |
| "Close the YouTube tab" · "Close Gmail" | Closes the browser tab showing that site |

For Steam games, the game is first asked to close normally (so it can save). If it's still running after ~4 seconds, it's stopped, exactly like Steam's Stop button. Then Steam is shown on the game's page.
To be asked before that stop, set `games.ask_before_force_stop: true`. Apps are only ever asked to close, never force-killed.
Tabs: Windows only lets apps see the tab that's *showing* in each browser window, so "close the YouTube tab" works when YouTube is the visible tab in one of your browser windows.

### Seeing what Capri opened
Whatever Capri opens (apps, games, folders, files, websites) is **brought to the front**, even if you were busy in another window. If the app was already running, its window just comes forward.

### Music & media
| Say | What happens |
|---|---|
| "Play Shelter by Porter Robinson" · "Play Blinding Lights" · "Play Porter Robinson" | Finds that song (or the artist's top song) and starts playing it |
| "Play my liked music" · "Play my favourites" · "Play my saved songs" | Plays your **Liked Music** on YouTube Music (the account you're signed in with in your browser) |
| "Play some music" · "Play some songs" | Same as liked music (change with `music.default: home` in settings) |
| "Play the top 10 songs" · "Play trending songs" · "Play the charts" | Plays the *Top 100 Songs Global* playlist |
| "Play top Hindi songs" · "Play lofi beats" · "Play 90s rock" · "Play workout music" · "Play chill vibes" | Finds a matching playlist and plays it |
| "Play [song] on YouTube" | Plays the top YouTube video |

If a YouTube Music or YouTube tab is the **active tab** in a browser window, Capri plays there instead of opening a new tab (she brings that window forward and loads the song in it). If the tab is in the background or only in the Opera GX sidebar, a new tab opens. Turn off with `web.reuse_youtube_tab: false`.

| Say | What happens |
|---|---|
| "Pause" · "Resume" · "Play" · "Stop the music" | Play/pause whatever is playing (works with the Opera GX sidebar, Spotify, browsers) |
| "Next song" · "Skip" | Next track |
| "Previous song" · "Go back a track" | Previous track |
| "Volume up" · "Louder" · "Turn it down" · "Mute" | System volume |
| "What's playing?" · "What song is this?" | Tells you the current track |

### Websites & search
| Say | What happens |
|---|---|
| "Open YouTube" · "Open Gmail" · "Open GitHub" · "Open Reddit" | Opens the site. Also works for maps, drive, calendar, twitch, netflix, chatgpt, claude, linkedin, amazon, wikipedia, x/twitter, whatsapp web |
| "Open example.com" | Opens any website address |
| "Look up the stock market" · "Search for RTX 5070 benchmarks" · "Find out who won last night" · "What's the latest on GTA 6" | Capri searches the web, reads the results and **tells you the answer** (sources shown in the chat) |
| "Google best ramen near me" · "Search cats on Google" | Opens a Google results page |
| "Search YouTube for Edgerunners trailer" | YouTube search results |

### Folders & files
| Say | What happens |
|---|---|
| "Open my downloads" · "Open documents" · "Open desktop" · "Open pictures" · "Open screenshots" | Opens the folder |
| "Open the Capricorn folder" · "Open the folder of Capricorn Assistant" · "Open the folder called Projects" | Finds a folder by name (Desktop, Documents, Downloads... up to 3 levels deep) |
| "Open the recycle bin" · "Open this PC" | Windows locations |
| "Open projects folder" | Your own aliases from `settings.yaml → shortcuts.folders` |
| "Open the resume pdf" · "Open budget spreadsheet" · "Open notes.txt" | Finds the file by name in your allowed folders and opens it |

### Capri's look
| Say | What happens |
|---|---|
| "Minimal mode" · "Enable minimal mode" · "Go minimal" · "Stealth mode" | Switches to **minimal mode**: just Capri's animated visor face, no chat bubbles (replies appear in the chat window, `Ctrl+Alt+C`). She stays on screen, idling with an occasional glitch, and talks when she replies |
| "Normal mode" · "Disable minimal mode" · "Turn off minimal" · "Back to normal" · "Full mode" · "Exit stealth mode" | Full Capri with chat bubbles again |
| "Hide yourself" · "Stay hidden" | Stop staying on screen. She still listens and pops up when called |
| "Show yourself" · "Stay on screen" | Stay on screen all the time |
| "Hide" · "Never mind" | Just dismiss her for now |

Also: **Capri dances while music is playing** (any player: YouTube Music tab, Opera GX sidebar, Spotify) whenever she's on screen in normal mode. She glitches in when she appears.
Minimal mode still shows a bubble for yes/no questions, so you can see what she's asking.
Both toggles are also in the tray menu (*Minimal mode*, *Always on screen*).

### System
| Say | What happens |
|---|---|
| "Lock the PC" · "Lock my laptop" | Locks Windows |
| "Put the PC to sleep" · "Shut down the computer" · "Restart" | Always asks "Are you sure?" first |
| "What time is it?" · "What's the date?" | Tells you |

### Talking to Capri
| Say | What happens |
|---|---|
| "Hi" · "Hello" · "What's up" | She greets you |
| "Thanks" · "Nice" · "Perfect" | She acknowledges it |
| "Never mind" · "Cancel" · "Bye" · "Go away" | She signs off and hides |
| Anything else ("tell me a joke", "explain black holes", "what should I play tonight?") | Chat with her AI brain (local, free) |

### Confirmations
When Capri asks *"Launch X?"*, say **"yes"** / **"do it"** / **"sure"** or **"no"** / **"cancel"**, or click the buttons.
A **yes is remembered**, so she won't ask again for the same app, folder, file or website. Sleep, shutdown and restart always ask.

---

## 2. Helper scripts (double-click)

| Script | What it does |
|---|---|
| **Running** | |
| `start.bat` | Start Capri (hidden in the tray). Only one copy ever runs |
| `stop.bat` | Quit Capri completely |
| `restart.bat` | Stop + start. Use after editing settings by hand |
| `debug.bat` | Run with a console window showing what Capri hears and does |
| `check.bat` | Health check: microphone, wake-word model, speech-to-text, Ollama |
| **Permissions** | |
| `permissions-full.bat` | Full access: any app, folder, file, website (power actions still ask) |
| `permissions-safe.bat` | Safe mode: asks before apps/files, only common folders |
| `forget-approvals.bat` | Forget every remembered "yes". Capri asks again |
| `edit-permissions.bat` | Open `permissions.yaml` in Notepad. Capri restarts when you close it |
| **Settings** | |
| `edit-settings.bat` | Open `settings.yaml` in Notepad. Capri restarts when you close it |
| `change-brain.bat` | Download another free AI model and switch to it (qwen3:8b smarter, llama3.2:3b faster) |
| `change-wake-sensitivity.bat` | Fewer accidental wake-ups (higher) or easier waking (lower). Default 0.55 |
| `change-size.bat` | Capri's size on screen. Default 0.42 |
| `toggle-always-visible.bat` | Keep Capri on screen when idle, or only when called |
| `toggle-minimal-mode.bat` | Switch between normal mode and minimal mode (animated face, no chat bubbles) |
| `use-gpu-speech.bat` | Faster speech-to-text on an NVIDIA GPU (~1 GB download) |
| `settings.bat` | The settings screen: every setting with explanations (also tray > Settings, the chat window, or "open settings") |
| **Voice & data** | |
| `install-capri-voice.bat` | Give Capri her own voice: free local voice cloning, ~4 GB one-time download. Add `--cpu` for no GPU |
| `test-voice.bat` | Type any line and hear Capri say it (checks a new `voices\capri.wav`) |
| `change-voice.bat` | Capri's voice / Windows voice / text only / auto |
| `change-voice-volume.bat` | Capri's voice louder or quieter (her voice only, not your music) |
| `split-voice-lines.bat` | Import recorded Capri lines (`lines-*.mp3` + `.txt`) as instant replies |
| `open-data-folder.bat` | Open `capricorn-data` (env, models, logs, settings, approvals) |
| `view-log.bat` | Live log: what Capri heard and how she handled it |
| `view-actions.bat` | History of every app, file, site and system action |
| **Maintenance** | |
| `update.bat` | After pulling new code: update packages + restart (keeps your data) |
| `run-tests.bat` | Run the automated tests (developers) |

Scripts that change a setting restart Capri automatically if she's running.
Start-with-Windows on/off: `install_startup.bat` / `remove_startup.bat` in the main folder.

---

## 3. Command line (advanced)

From the main folder, with `PY = capricorn-data\python\Scripts\python.exe`:

```
%PY% -m capricorn                          run Capricorn (with console)
%PY% -m capricorn --check                  health check
%PY% -m capricorn --profile full|safe      write a permissions profile
%PY% -m capricorn --forget-approvals       clear remembered approvals
%PY% -m capricorn --get brain.model        print a setting
%PY% -m capricorn --set ui.scale=0.5       change a setting (repeatable: --set a=1 --set b=2)
%PY% tools\split_voice_lines.py "<folder>" [--transcribe-missing]
```

Setting names are the dotted paths in `capricorn-data\settings.yaml`, e.g. `wake.min_confidence`, `stt.model`, `brain.model`, `ui.hide_after`, `ui.hotkey`, `voice.engine`, `music.service`.
