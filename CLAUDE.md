# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`whisper-dictate-tw` — a fully offline **Traditional-Chinese voice dictation** app for Windows.
Press a global hotkey, speak, and the transcript is typed straight into whatever input field the
cursor is in. No cloud. (This repo previously hosted a local voice *agent* with an Ollama LLM
reply loop; that half was removed — this is now a pure dictation tool.)

## Pipeline

```
[mic 16kHz] -> [faster-whisper ASR] -> [OpenCC s2twp 繁化] -> [type at cursor (pynput)]
```

Default model is `large-v3-turbo` (multilingual, ~large-v3 accuracy, several× faster). ASR runs on
CPU int8 by default; CUDA is optional. OpenCC `s2twp` is a deterministic post-process that pins
Whisper's Chinese output to Traditional (Taiwan) — Whisper alone may emit Simplified or a mix.

## Modules

- [asr.py](asr.py) — `SpeechToText` (faster-whisper `WhisperModel`; cuda→cpu int8 fallback).
  `transcribe_segments()` yields per-segment text; `transcribe()` joins. Accepts an ndarray or a
  file path (mp3/m4a/wav… decoded via the bundled `av`).
- [dictation_engine.py](dictation_engine.py) — `DictationEngine`: state machine
  idle→recording→processing. `toggle()` for mic; `transcribe_file(path, on_segment)` for import.
  Applies OpenCC, types at cursor via `pynput`, reports state/result via callbacks (UI-agnostic).
- [notes.py](notes.py) — `NotesStore`, SQLite (stdlib) at `%APPDATA%\voice2text-dictate\notes.db`.
- [hotkey_capture.py](hotkey_capture.py) — `HotkeyEdit`, a press-to-set widget; converts a Qt key
  event to a pynput hotkey string (e.g. `<ctrl>+<alt>+d`), validated with `keyboard.HotKey.parse`.
- [gui.py](gui.py) — PySide6 app: `QMainWindow` with tabs (聽寫/筆記歷史/音檔匯入/設定) +
  `QSystemTrayIcon`. Closing the window hides to tray. Cross-thread UI updates go through the
  `Bridge` QObject signals.
- [config.py](config.py) — ASR fallback defaults; each overridable by a same-named env var. The
  GUI's own settings live in `settings.json` and are passed explicitly to `SpeechToText`.

## Commands

```powershell
py -3.13 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pythonw gui.py                 # background (no console); python gui.py to see messages

# package
pip install -r requirements-build.txt
pyinstaller gui.spec           # -> dist\whisper-dictate-tw\ (model NOT bundled)
iscc installer.iss             # -> setup.exe (needs Inno Setup)
```

## Verifying changes

No automated test suite; the GUI needs a real desktop (tray, mic, cursor focus) for full end-to-end.
For headless checks, drive Qt with `QT_QPA_PLATFORM=offscreen` and stub or use the light `tiny`
model (already caching turbo is ~1.6GB). Useful isolation checks:

```powershell
# ASR file path (av decode + segments) with a light model
python -c "from dictation_engine import DictationEngine as E; e=E(model='tiny'); e.load_model(); print(repr(e.transcribe_file('sample.wav')))"

# OpenCC 繁化
python -c "import opencc; print(opencc.OpenCC('s2twp').convert('软件里的字符串'))"
```

## Constraints when editing

- **Offline only** — dictation and import never hit the network; the sole exception is the one-time
  Hugging Face model download on first run.
- **Traditional-Chinese focus** — keep the OpenCC `s2twp` step; don't offer Simplified as the default.
- **PySide6 object lifetime** — keep strong Python refs to `QMainWindow`/tray/`Bridge`, and give Qt
  objects parents. A discarded reference gets GC'd and segfaults the process with no traceback.
- **Qt threading** — never touch widgets from a worker thread; marshal via `Bridge` signals.
- **Deps** — faster-whisper, sounddevice, numpy, pynput, PySide6, opencc. faster-whisper's
  CTranslate2 backend replaces torch/transformers; don't pull those back in.
