# Agents

## Project

This is `readit`, a Python CLI wrapper around piper-tts for text-to-speech on macOS.

## Stack

- Python 3.14+
- piper-tts (dependency in pyproject.toml, installed via `uv pip install -e .`)
- macOS `afplay` for audio playback, `pbpaste` for clipboard access
- Voice model: `en_US-kristin-medium.onnx` in project root

## Structure

- `readit.py` — single-file CLI module, installed as console script via pyproject.toml

## Commands

- Run: `readit "text"`
- Interactive mode: `readit` (launches automatically when no input provided)
- Interactive mode (explicit): `readit -i`
- Typecheck: `mypy readit.py --ignore-missing-imports`
- Test (unit): `pytest -v`
- Test (smoke): `echo "test" | readit -o /dev/null`

## Testing

- **Always write tests first (TDD)** — create failing tests before implementing features
- Test file: `test_readit.py` using `pytest`
- Tests use dependency injection (fake `run`, `stdin`, `stdout`, `stderr`) to avoid real subprocess calls
- The `readit` module is imported directly (`import readit as _readit`)
- Run full test suite before and after every change: `pytest -v`

## Conventions

- Single-file script, installed as console script via pyproject.toml
- Use `argparse` for CLI argument parsing
- Use `subprocess` to invoke piper and afplay
- Default model path is resolved relative to the script location
