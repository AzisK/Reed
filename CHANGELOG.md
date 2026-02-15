# Changelog

## Unreleased

### Platform abstraction
- **macOS and Linux support**: Audio playback and clipboard commands are now auto-detected at runtime instead of being hardcoded to macOS tools.
  - Audio: `afplay` (macOS), `paplay`/`aplay`/`ffplay` (Linux)
  - Clipboard: `pbpaste` (macOS), `wl-paste`/`xclip`/`xsel` (Linux)
- **`get_text()` now uses injected `run`**: The clipboard path previously called `subprocess.run` directly, bypassing the dependency injection pattern used everywhere else. Now consistent.

### Rich terminal UI
- **Added Rich library** for styled terminal output (colors, panels, spinners).
- **Interactive banner** with styled markup replaces plain-text banner lines.
- **Progress feedback**: Status messages for generation and playback with timing info.
- **Styled error panels**: Errors displayed in red-bordered Rich panels.
- **Styled save confirmation**: Output-saved messages shown in green-bordered panels.

### Interactive mode
- **Replaced quit words with slash commands**: `quit`/`exit` → `/quit`/`/exit`. Removed `:q`. Plain words can now be spoken without accidentally exiting.
- **Added `/help` command**: Shows available commands in a styled panel.
- **Added `/clear` command**: Clears screen and reprints the banner.
- **Added `/replay` command**: Replays the last spoken text.
- **Integrated `prompt_toolkit`**: Interactive mode now uses `PromptSession` with fish-style auto-suggest for commands as you type. Handles bracketed paste natively.
- **Removed manual bracketed paste handling**: The old `select`-based input batching and escape sequence stripping are replaced by prompt_toolkit's built-in support.

### API improvements
- **`print_fn` dependency injection**: All output functions accept an optional `print_fn` parameter, replacing `stdout`/`stderr` injection for testability.
- **`clear_fn` injection**: `interactive_loop` accepts a `clear_fn` parameter for testable screen clearing.
- **`main()` returns `int`** instead of calling `sys.exit()` internally. The `__main__` block does `sys.exit(main())`.
- **`get_text()` accepts injected `stdin`**: No longer reads `sys.stdin` directly.
- **`interactive_loop` simplified**: Accepts a `prompt_fn` for dependency injection instead of fake stdin objects.

### Error handling
- **Added `ReedError` exception**: Helpers (`get_text`, `speak_text`) now raise `ReedError` instead of calling `sys.exit(1)` directly, making them reusable and testable.
- **`pbpaste` and `afplay` return codes checked**: Previously ignored; now raises `ReedError` on failure.

### Packaging
- **Added `pyproject.toml`**: `reed` is now installable as a package via `uv pip install -e .` with a `reed` console script entry point.
- **Renamed `reed` → `reed.py`**: Enables standard Python imports; no more `SourceFileLoader` hack in tests.
- **Dependencies declared**: `piper-tts`, `prompt-toolkit`, and `rich` listed in `pyproject.toml`; `mypy` and `pytest` as optional dev dependencies.

### Tests
- **44 tests** (up from 25): added coverage for platform detection (`_default_play_cmd`, `_default_clipboard_cmd`), clipboard `run` injection, `/replay` (with and without prior text), `/clear` (verifies `clear_fn` called), afplay failure, missing model error, empty text error, `ReedError` propagation through `main`, `_should_enter_interactive` with `None` stdin, and `get_text` with text args.
- Banner test now captures `print_fn` output and verifies the banner was actually printed.
- `TestMainErrors` uses Rich `Console` capture for end-to-end error message verification.
