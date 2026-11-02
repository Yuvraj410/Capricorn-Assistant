# Capri voice samples

Source: fish.audio voice "Capri Cyberpunk Edgerunners" (ef387f44931d4ab6a3f959a083c9fbb1), generated 2026-11-01.
**Personal use only: do not commit to the public repo.** (These belong in models/voices/capri/ later, which is git-ignored.)

## Current bundle layout

The project owner requested these samples be included with the repository. The original source restriction above is retained for visibility; inclusion does not change the recordings' licence or grant redistribution rights under the code's MIT licence.

- `capri.wav` and `capri.txt`: the working 14.7-second reference and transcript from the installed copy.
- `capri-calm.mp3`: a byte-for-byte copy of the original `Hmm...` download for calm delivery.
- `capri-playful.mp3`: a byte-for-byte copy of the original `Whoa...` download for energetic/playful delivery.
- Original MP3 filenames and available transcripts are preserved below; `to-record/` contains scripts, not additional recorded moods.
- Setup selects `capri.wav` and installs the two named mood samples when Capri's own voice is selected. It also preserves this source folder in the installation for choosing alternate takes later.
- Unsplit line packs are retained as source material; they are not passed to the voice model as mood references. Discarded incorrect splits in `_to_delete/` are excluded.

## Long clips (reference audio for local voice cloning, OpenAudio S1-mini)
Each `.mp3` has a matching `.txt` transcript.
- `...16-05-Hey,-choom...` / `...16-06-...`: intro script (two takes)
- `...16-08-Whoa...`: energetic script
- `...16-08-Hmm...`: calm script
- `...16-03-Hey-there!...`: **transcript missing**. Paste the original text into a `.txt` with the same name, or Whisper will transcribe it during Phase 0 setup on Windows.

## Line packs
`lines-1.mp3` (29 lines) and `lines-2.mp3` (14 lines), with the full text in `lines-1.txt` / `lines-2.txt`.

**Not split yet.** The first attempt split them by silence alone and got the boundaries wrong (e.g. one clip held "Ha! Okay, that was good. Whoa, seriously? Ugh. Fine."). It's in `_to_delete/`, and you can delete that folder.
They'll be split in Phase 0 on Windows with Whisper **word timestamps**, which cuts each line at its actual words, then double-checked by transcribing every clip and comparing it to the text. Speech recognition models couldn't be downloaded in the environment used so far, so it couldn't be done reliably before then.
