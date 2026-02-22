# Agents

## Project

This is `reed`, a convenient CLI for text-to-speech using piper-tts.

## Stack

- uv — package manager and virtual environment tool
- Python 3.14+
- piper-tts (dependency in pyproject.toml, run via `uv run reed`)
- pypdf (PDF text extraction)
- stdlib `zipfile` + `xml.etree` (EPUB reading — no external dependency)
- macOS `afplay` for audio playback, `pbpaste` for clipboard access
- Linux: `paplay`/`aplay`/`ffplay` for audio, `wl-paste`/`xclip`/`xsel` for clipboard
- Windows: `powershell`/`ffplay` for audio, `powershell Get-Clipboard` for clipboard
- Rich (terminal UI library for styled output)
- Voice models stored in `~/.local/share/reed/` (Linux/macOS) or `%LOCALAPPDATA%\reed\` (Windows)
- `prompt_toolkit` (interactive prompt with history and autocomplete)
- `pathvalidate` (required by piper-tts dependency chain — do NOT remove)

## Structure

- `reed.py` — single-file CLI module, installed as console script via pyproject.toml
- `test_reed.py` — comprehensive test suite (TDD approach)
- `ARCHITECTURE.md` — detailed system design, component diagrams, and data flow
- `ROADMAP.md` — feature roadmap with priorities and dependencies

Start here: Read `ARCHITECTURE.md` before implementing features that touch playback, interactive mode, or file processing.

## Commands

- Run: `reed 'text'`
- Read PDF: `reed -f doc.pdf` or `reed -f doc.pdf --pages 1,3-5`
- Read EPUB: `reed -f book.epub` or `reed -f book.epub --pages 1,3-5`
- Interactive mode: `reed` (launches automatically when no input provided)
  - Drag and drop PDF/EPUB files to read them aloud (fastest method)
  - `/load <path>` — Load and read a PDF or EPUB file (useful in SSH/tmux)
- List voices: `reed voices`
- Download voice: `reed download en_US-amy-medium`
- Typecheck: `mypy reed.py --ignore-missing-imports`
- Sync deps: `uv sync`
- Test (unit): `uv run pytest`
- Test (smoke): `echo 'test' | reed -o /dev/null`

## Testing

- Always write tests first (TDD) — create failing tests before implementing features
- Test file: `test_reed.py` using `pytest`
- Tests use dependency injection (fake `run`, `stdin`, `print_fn`) to avoid real subprocess calls
- The `reed` module is imported directly (`import reed as _reed`)
- Run full test suite before and after every change: `uv run pytest -v`
- New components: Add tests for `PlaybackController` state transitions, thread safety, and signal handling

## Workflow

- Plan first: Before implementing any feature or fix, outline your approach and identify affected components
- Always run tests after code changes: Verify changes don't break existing functionality
- Use a subagent for running tests to avoid polluting the main conversation context with verbose output

## Conventions

- Single-file script, installed as console script via pyproject.toml
- Use `argparse` for CLI argument parsing
- Use `subprocess` to invoke piper and platform audio player
- Default model auto-downloaded to `_data_dir()` on first run
- `ReedConfig` dataclass for core configuration
- Thread safety: Use `threading.Lock` for shared state in `PlaybackController`
- Non-blocking playback: Interactive mode uses `PlaybackController`; file/output modes use blocking `subprocess.run()`
- Platform checks: Use `os.name == "posix"` for Unix-specific behavior (SIGSTOP/SIGCONT)
- Python 3.14+ syntax is allowed — e.g. `except A, B:` without parentheses (PEP 758), and other 3.14 features. Do not flag these as errors.
- Use `X | None` instead of `Optional[X]` — project uses modern union syntax throughout

 ## UI Development

 - Use Rich library for terminal UI enhancements (colors, panels, spinners, tables)
 - Banner styled with rich markup in `BANNER_MARKUP` constant
 - Visual feedback includes spinner during TTS generation
 - Commands available in interactive mode: `/quit`, `/exit`, `/help`, `/clear`, `/replay`, `/load`
 - Tab autocomplete available for commands
 - Include `print_fn` parameter for testability with dependency injection
 - Playback state: Future `/pause`, `/play`, `/stop` commands will wire to `PlaybackController` methods
 - File loading: When reading multi-page PDFs or multi-chapter EPUBs, each page/chapter waits for the previous one to complete
 - Drag-and-drop: Primary method for loading files; `/load` command is for remote terminals
