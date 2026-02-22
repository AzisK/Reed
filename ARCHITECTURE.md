# Reed Architecture

This document describes the internal architecture of reed, a CLI text-to-speech application built on piper-tts.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         reed CLI                                │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  main()     │  │  get_text()  │  │  speak_text()          │ │
│  │  - arg parse│  │  - file I/O  │  │  - piper TTS           │ │
│  │  - routing  │  │  - clipboard │  │  - audio playback      │ │
│  └──────┬──────┘  └──────────────┘  └───────────┬────────────┘ │
│         │                                        │              │
│         ▼                                        ▼              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              PlaybackController (interactive mode)        │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │   │
│  │  │ Background  │  │  Pause/      │  │  Process        │  │   │
│  │  │ Thread      │  │  Resume      │  │  Management     │  │   │
│  │  └─────────────┘  └──────────────┘  └─────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │         External Tools        │
              │  piper-tts │ afplay/paplay    │
              └───────────────────────────────┘
```

## Core Components

### 1. Entry Point (`main()`)

**Location:** `reed.py:main()`

**Responsibilities:**
- Parse CLI arguments with `argparse`
- Resolve voice model path (name → `~/.local/share/reed/`)
- Route to appropriate mode:
  - **Interactive mode** — no input provided, TTY detected
  - **File mode** — PDF/EPUB with optional page/chapter selection
  - **One-shot mode** — text argument, clipboard, or stdin
- Handle special commands: `reed voices`, `reed download <voice>`

**Flow:**
```
argv → argparse → resolve model → ensure_model() → route
                                              ├─ interactive_loop()
                                              ├─ _iter_pdf_pages() / _iter_epub_chapters()
                                              └─ get_text() → speak_text()
```

---

### 2. Input Pipeline (`get_text()`, `_iter_*()`)

**Location:** `reed.py:get_text()`, `_iter_pdf_pages()`, `_iter_epub_chapters()`

**Responsibilities:**
- Extract text from various sources
- Normalize and chunk text for TTS

**Input Sources:**
| Source | Implementation |
|--------|----------------|
| Text argument | `args.text` joined with spaces |
| File | `Path.read_text()` |
| Clipboard | `_default_clipboard_cmd()` → subprocess |
| stdin | `stdin.read()` if not TTY |
| PDF | `pypdf.PdfReader` → `_iter_pdf_pages()` |
| EPUB | `zipfile` + `xml.etree` → `_iter_epub_chapters()` |

**PDF Processing:**
```
PDF file → PdfReader → extract_text() per page → yield (page_num, total, text)
```

**EPUB Processing:**
```
EPUB file → zipfile → META-INF/container.xml → OPF spine → XHTML chapters
         → _strip_html() → yield (chapter_num, total, text)
```

---

### 3. TTS Generation (`build_piper_cmd()`, `speak_text()`)

**Location:** `reed.py:build_piper_cmd()`, `speak_text()`

**Responsibilities:**
- Construct piper-tts command line
- Generate WAV audio from text
- Route audio to player or file

**Piper Command:**
```python
[
    sys.executable, "-m", "piper",
    "--model", "<path>.onnx",
    "--length-scale", "<speed>",
    "--volume", "<volume>",
    "--sentence-silence", "<silence>",
    "--output-file", "<output.wav>"  # optional
]
```

**Two Playback Modes:**

| Mode | Implementation | Use Case |
|------|----------------|----------|
| **Blocking** | `subprocess.run()` | File output, non-interactive |
| **Non-blocking** | `PlaybackController.play()` | Interactive mode |

---

### 4. Playback Controller (Non-blocking)

**Location:** `reed.py:PlaybackController`, `PlaybackState`

**Purpose:** Enable pause/resume/stop controls without blocking the interactive prompt.

**Architecture:**
```
┌─────────────────────────────────────────────────────────┐
│                  PlaybackController                      │
│  ┌────────────────────────────────────────────────────┐ │
│  │  State Machine: IDLE → PLAYING → PAUSED → PLAYING  │ │
│  │                      PLAYING → STOPPED → IDLE      │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────┐    ┌────────────────────────────┐   │
│  │ play(text)     │───▶│ Background Thread          │   │
│  │ pause()        │    │  1. Run piper (Popen)      │   │
│  │ resume()       │    │  2. Run player (Popen)     │   │
│  │ stop()         │    │  3. Wait & cleanup         │   │
│  └────────────────┘    └────────────────────────────┘   │
│                                                          │
│  ┌────────────────┐    ┌────────────────────────────┐   │
│  │ Unix (POSIX)   │    │ Windows (NT)               │   │
│  │ SIGSTOP/SIGCONT│    │ Pause/resume not supported │   │
│  └────────────────┘    └────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Key Methods:**

| Method | Description | Platform |
|--------|-------------|----------|
| `play(text, config)` | Start playback in background thread | All |
| `pause()` | Send `SIGSTOP` to player process | Unix only |
| `resume()` | Send `SIGCONT` to player process | Unix only |
| `stop()` | Terminate piper + player processes | All |
| `wait()` | Block until playback completes | All |
| `is_playing()` | Check current state | All |
| `get_current_text()` | Get last spoken text (for replay) | All |

**Thread Safety:**
- All state mutations protected by `threading.Lock`
- `_stop_event` (threading.Event) for clean shutdown
- Daemon threads prevent hanging on exit

**Process Management:**
```python
# Generation
piper_proc = Popen(piper_cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
piper_proc.communicate(input=text.encode())

# Playback
player_proc = Popen([*play_cmd, tmp_path])
player_proc.wait()  # Blocks thread, not main loop
```

---

### 5. Interactive Loop

**Location:** `reed.py:interactive_loop()`

**Responsibilities:**
- Display prompt with `prompt_toolkit`
- Handle commands: `/quit`, `/help`, `/clear`, `/replay`
- Route text to `speak_text()` with controller

**Flow:**
```
┌─────────────────────────────────────────────────────────┐
│                  interactive_loop()                      │
│                                                          │
│  while True:                                             │
│    text = prompt_fn()  # prompt_toolkit                  │
│    if text in QUIT_WORDS: return 0                       │
│    if text == "/help": print_help(); continue            │
│    if text == "/clear": clear_fn(); continue             │
│    if text == "/replay":                                 │
│       controller.get_current_text() → speak_line()       │
│    else:                                                 │
│       speak_line(text)  # non-blocking via controller    │
└─────────────────────────────────────────────────────────┘
```

**Integration with Controller:**
```python
# In main()
controller = PlaybackController(print_fn=print_fn)
interactive_loop(
    speak_line=lambda line: speak_text(
        line, config, controller=controller  # Non-blocking
    ),
    controller=controller,  # For replay
)
```

---

### 6. Audio Player Detection

**Location:** `reed.py:_default_play_cmd()`

**Strategy:** Detect available player based on OS and installed tools.

| OS | Priority Order |
|----|----------------|
| **macOS** | `afplay` (bundled) |
| **Linux** | `paplay` → `aplay` → `ffplay` |
| **Windows** | PowerShell `SoundPlayer` → `ffplay` |

**Clipboard Detection:**
| OS | Priority Order |
|----|----------------|
| **macOS** | `pbpaste` (bundled) |
| **Linux** | `wl-paste` → `xclip` → `xsel` |
| **Windows** | PowerShell `Get-Clipboard` |

---

## Data Flow

### Interactive Mode (Non-blocking)
```
User input → prompt_toolkit → interactive_loop
                              │
                              ▼
                     speak_text(controller=c)
                              │
                              ▼
                     controller.play(text, config)
                              │
              ┌───────────────┴───────────────┐
              │ Background Thread             │
              │  1. piper → temp WAV          │
              │  2. player → audio output     │
              │  3. cleanup temp file         │
              └───────────────────────────────┘
                              │
                              ▼
                     Prompt returns immediately
```

### File Mode (Blocking)
```
PDF/EPUB → _iter_*_pages() → for each chunk:
                                │
                                ▼
                       speak_text(config, run=subprocess.run)
                                │
                                ▼
                       piper (run) → player (run)
                                │
                                ▼
                       Next chunk (sequential)
```

### Output Mode (Blocking)
```
speak_text(config.output=Path("out.wav"))
         │
         ▼
piper --output-file out.wav
         │
         ▼
Return (no playback)
```

---

## State Management

### PlaybackState Enum
```python
class PlaybackState(Enum):
    IDLE = auto()      # No active playback
    PLAYING = auto()   # Currently playing
    PAUSED = auto()    # Paused (Unix only)
    STOPPED = auto()   # Stopped mid-playback
```

### Controller State Transitions
```
        ┌──────────────────────────────────────────┐
        │                                          │
        ▼                                          │
     ┌──────┐    play()     ┌─────────┐           │
     │ IDLE │──────────────▶│ PLAYING │◀──────────┤
     └──────┘               └────┬────┘           │
        ▲                       │                 │
        │          stop()       │ pause()         │
        │          ┌────────────┘                 │
        │          ▼                              │
     ┌────────┐  stop()    ┌─────────┐  resume()  │
     │ STOPPED│◀───────────│ PAUSED  │────────────┘
     └────────┘            └─────────┘
```

---

## Platform Abstraction

### Unix (Linux/macOS)
- **Pause/Resume:** `SIGSTOP` / `SIGCONT` signals
- **Audio:** `afplay` (macOS), `paplay`/`aplay`/`ffplay` (Linux)
- **Clipboard:** `pbpaste` (macOS), `wl-paste`/`xclip`/`xsel` (Linux)

### Windows
- **Pause/Resume:** Not supported (returns `False`)
- **Audio:** PowerShell `SoundPlayer` or `ffplay`
- **Clipboard:** PowerShell `Get-Clipboard`

---

## Error Handling

### ReedError
Custom exception for user-facing errors:
```python
class ReedError(Exception):
    """Raised for reed-specific errors (model not found, no player, etc.)"""
```

### Error Categories
| Error | Handling |
|-------|----------|
| Model not found | Auto-download from Hugging Face |
| No audio player | `ReedError` → printed panel → exit 1 |
| Piper failure | `ReedError` with stderr output |
| Process termination failure | Catch `ProcessLookupError`, `TimeoutExpired` |

---

## Testing Strategy

### Test Categories
1. **Unit Tests** — Individual functions (`build_piper_cmd`, `_strip_html`)
2. **Integration Tests** — `main()` with mocked subprocess
3. **Controller Tests** — `PlaybackController` state transitions
4. **Platform Tests** — OS-specific behavior via `monkeypatch`

### Mocking Patterns
```python
# Mock subprocess.run
def fake_run(cmd, **kwargs):
    return types.SimpleNamespace(returncode=0, stderr="")

# Mock PlaybackController.play
def fake_play(self, text, config):
    played_texts.append(text)

# Mock platform detection
monkeypatch.setattr("reed.platform.system", lambda: "Darwin")
```

---

## Dependencies

### Runtime
| Package | Purpose | Optional |
|---------|---------|----------|
| `piper-tts` | Text-to-speech generation | No |
| `prompt_toolkit` | Interactive prompt | No |
| `rich` | Terminal formatting | No |
| `pypdf` | PDF text extraction | Yes (PDF support) |

### System Tools (one per category)
| Category | macOS | Linux | Windows |
|----------|-------|-------|---------|
| **Audio** | `afplay` | `paplay`, `aplay`, `ffplay` | PowerShell, `ffplay` |
| **Clipboard** | `pbpaste` | `wl-paste`, `xclip`, `xsel` | PowerShell |

---

## Future Extensions

### Phase 1.3 — Playback Controls
Add interactive commands `/pause`, `/play`, `/stop` wired to `PlaybackController`.

### Phase 3.1 — Bookmarks
Persist reading position in `~/.local/share/reed/bookmarks.json`:
```json
{
  "/abs/path/to/book.pdf": {
    "page": 12,
    "char_offset": 340,
    "timestamp": "2026-02-18T10:00:00"
  }
}
```

### Phase 4.1 — Streaming Audio
Replace temp file with pipe-based streaming:
```
piper --output-raw | ffplay -f s16le -ar 22050 -ac 1 -
```
Requires refactoring `PlaybackController` to use `stdin=PIPE` for player.

---

## File Structure

```
reed/
├── reed.py              # Main module (all logic)
├── test_reed.py         # Tests (TDD style)
├── pyproject.toml       # Package metadata, dependencies
├── ARCHITECTURE.md      # This document
├── README.md            # User documentation
└── ROADMAP.md           # Feature roadmap
```

**Note:** `reed.py` is intentionally monolithic (~1000 lines) to minimize dependencies and simplify distribution. Functions are organized by layer:
1. Imports & constants
2. Exceptions & enums
3. Core classes (`PlaybackController`)
4. Helper functions (`_data_dir`, `_model_url`)
5. Input pipeline (`get_text`, `_iter_*`)
6. TTS pipeline (`build_piper_cmd`, `speak_text`)
7. UI functions (`print_*`, `interactive_loop`)
8. Entry point (`main`)
