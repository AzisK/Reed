# Agents

## Project

This is `reed`, a Python CLI wrapper around piper-tts for text-to-speech on macOS.

## Stack

- uv — package manager and virtual environment tool
- Python 3.14+
- piper-tts (dependency in pyproject.toml, installed via `uv pip install -e .`)
- macOS `afplay` for audio playback, `pbpaste` for clipboard access
- Rich (terminal UI library for styled output)
- Voice model: `en_US-kristin-medium.onnx` in project root

## Structure

- `reed.py` — single-file CLI module, installed as console script via pyproject.toml

## Commands

- Run: `reed "text"`
- Interactive mode: `reed` (launches automatically when no input provided)
- Interactive mode (explicit): `reed -i`
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
- Use `subprocess` to invoke piper and afplay
- Default model path is resolved relative to the script location

 ## UI Development

 - Use Rich library for terminal UI enhancements (colors, panels, spinners, tables)
 - Bannerstyled with rich markup in `BANNER_MARKUP` constant
 - Visual feedback includes spinner during TTS generation
 - Commands available in interactive mode: `/quit`, `/exit`, `/help`, `/clear`, `/replay`
 - Tab autocomplete available for commands
 - Include `print_fn` parameter for testability with dependency injection

## Git

- Do NOT add `Co-authored-by` or `Amp-Thread-ID` trailers to commits
