# Agents

## Project

This is `reed`, a convenient CLI for text-to-speech using piper-tts.

## Stack

- uv — package manager and virtual environment tool
- Python 3.14+
- piper-tts (dependency in pyproject.toml, installed via `uv pip install -e .`)
- macOS `afplay` for audio playback, `pbpaste` for clipboard access
- Linux: `paplay`/`aplay`/`ffplay` for audio, `wl-paste`/`xclip`/`xsel` for clipboard
- Rich (terminal UI library for styled output)
- Voice models stored in `~/.local/share/reed/` (Linux/macOS) or `%LOCALAPPDATA%\reed\` (Windows)

## Structure

- `reed.py` — single-file CLI module, installed as console script via pyproject.toml

## Commands

- Run: `reed "text"`
- Interactive mode: `reed` (launches automatically when no input provided)
- List voices: `reed voices`
- Download voice: `reed download en_US-amy-medium`
- Typecheck: `mypy reed.py --ignore-missing-imports`
- Test (unit): `pytest -v`
- Test (smoke): `echo "test" | reed -o /dev/null`

## Testing

- **Always write tests first (TDD)** — create failing tests before implementing features
- Test file: `test_reed.py` using `pytest`
- Tests use dependency injection (fake `run`, `stdin`, `print_fn`) to avoid real subprocess calls
- The `reed` module is imported directly (`import reed as _reed`)
- Run full test suite before and after every change: `pytest -v`

## Conventions

- Single-file script, installed as console script via pyproject.toml
- Use `argparse` for CLI argument parsing
- Use `subprocess` to invoke piper and platform audio player
- Default model auto-downloaded to `_data_dir()` on first run
- `ReedConfig` dataclass for core configuration (not `argparse.Namespace`)

 ## UI Development

 - Use Rich library for terminal UI enhancements (colors, panels, spinners, tables)
 - Bannerstyled with rich markup in `BANNER_MARKUP` constant
 - Visual feedback includes spinner during TTS generation
 - Commands available in interactive mode: `/quit`, `/exit`, `/help`, `/clear`, `/replay`
 - Tab autocomplete available for commands
 - Include `print_fn` parameter for testability with dependency injection

## Git

- Do NOT add `Co-authored-by` or `Amp-Thread-ID` trailers to commits
