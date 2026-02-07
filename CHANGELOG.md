# Changelog

## Unreleased

### Packaging
- **Added `pyproject.toml`**: `readit` is now installable as a package via `uv pip install -e .` with a `readit` console script entry point.
- **Renamed `readit` → `readit.py`**: Enables standard Python imports; no more `SourceFileLoader` hack in tests.
- **Dependencies declared**: `piper-tts` and `prompt-toolkit` listed in `pyproject.toml`; `mypy` and `pytest` as optional dev dependencies (`uv pip install -e ".[dev]"`).

### Interactive mode
- **Replaced quit words with slash commands**: `quit`/`exit` → `/quit`/`/exit` (`:q` retained). Plain words can now be spoken without accidentally exiting.
- **Integrated `prompt_toolkit`**: Interactive mode now uses `PromptSession` with fish-style auto-suggest for commands as you type. Handles bracketed paste natively.
- **Removed manual bracketed paste handling**: The old `select`-based input batching and escape sequence stripping are replaced by prompt_toolkit's built-in support.

### Error handling
- **Added `ReaditError` exception**: Helpers (`get_text`, `speak_text`) now raise `ReaditError` instead of calling `sys.exit(1)` directly, making them reusable and testable.
- **`pbpaste` and `afplay` return codes checked**: Previously ignored; now raises `ReaditError` on failure.

### API improvements
- **`main()` returns `int`** instead of calling `sys.exit()` internally. The `__main__` block does `sys.exit(main())`.
- **`get_text()` accepts injected `stdin`**: No longer reads `sys.stdin` directly, fixing an inconsistency where `main(stdin=...)` only partially worked.
- **`interactive_loop` simplified**: Accepts a `prompt_fn` for dependency injection instead of fake stdin objects. Quit words normalized to a lowercase set internally.

### Tests
- Added 7 new tests: `_should_enter_interactive` (6 branches), `get_text` stdin injection.
- Removed unused imports (`MagicMock`, `call`, `patch`).
- Tests now inject `prompt_fn` instead of fake stdin/tty objects.
