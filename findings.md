# Reed Code Review Findings

**Date:** 2026-02-22
**Scope:** Full repo — `reed.py` (1145 LOC), `test_reed.py` (1955 LOC), `pyproject.toml`
**Status:** 127 tests pass, 0 mypy errors

---

## 🐛 Bugs

### B1. `print_help()` — Cyan styling silently lost
**File:** `reed.py:678-682`
**Severity:** Low (cosmetic)

```python
for cmd, desc in COMMANDS.items():
    cmd_text = Text(cmd)
    cmd_text.stylize("cyan")
    text.append(f"\n{cmd_text} - {desc}")  # ← str(cmd_text) strips style
```

`f"\n{cmd_text}"` calls `__str__()` on the `Text` object, which returns plain text — the cyan style is discarded. The `/help` output renders all commands unstyled.

**Fix:** Use `text.append("\n")` then `text.append(cmd_text)` then `text.append(f" - {desc}")`.

---

### B2. Test passes wrong type to `speak_text`
**File:** `test_reed.py:620-622`
**Severity:** Low (test-only, works by accident)

```python
args = _make_args()  # returns argparse.Namespace
with pytest.raises(ReedError, match="playback error"):
    speak_text("hi", args, run=fake_run)  # ← expects ReedConfig, gets Namespace
```

`speak_text` expects `config: ReedConfig` but receives an `argparse.Namespace`. Works only because both objects have the same attribute names. Should use `_make_config()`.

---

## 🧹 Clean Code

### C1. Unused dependency: `pathvalidate`
**File:** `pyproject.toml:14`
**Severity:** Medium (bloats install)

`pathvalidate` is listed in `[project.dependencies]` but never imported in `reed.py`. Dead dependency.

---

### C2. Use modern `X | None` syntax instead of `Optional[X]`
**File:** `reed.py` (throughout)
**Severity:** Low (style)

Project requires Python 3.14+. All `Optional[X]` can be `X | None`, and `list[str]` is already used. The `from typing import Optional` import can be removed. Same for `Sequence`, `Callable`, `Iterator`, `TextIO` which can come from `collections.abc` or be used directly.

Currently mixed: `Optional[Path]` alongside `list[str]` — inconsistent.

---

### C3. Complex EPUB empty-chapter skip logic in `main()`
**File:** `reed.py:1089-1127`
**Severity:** Medium (readability)

The 40-line block with `spoken` set, inner for-loop, `for...else`, and `continue`/`break` is the hardest-to-read section. It handles:
1. Normal chapters
2. Empty chapters with a subsequent non-empty fallback
3. Empty chapters with no subsequent text

This could be extracted to `_iter_epub_chapters_skipping_empty()` to keep `main()` cleaner and make the logic independently testable.

---

### C4. Resource management — `_load_epub_spine` returns unclosed `ZipFile`
**File:** `reed.py:518-573`
**Severity:** Medium (resource leak risk)

`_load_epub_spine` opens a `ZipFile` and returns it inside tuples. The caller is responsible for closing it. `_iter_epub_chapters` closes it in a `finally` block, but the `main()` EPUB path doesn't — it calls `_load_epub_spine` separately (line 1089) and the returned `zf` is never explicitly closed.

**Fix:** Make `_load_epub_spine` a context manager, or close `chapters[0][1]` in `main()`.

---

### C5. `_data_dir()` creates directory on every call
**File:** `reed.py:240-248`
**Severity:** Low (performance)

`mkdir(parents=True, exist_ok=True)` is called every time `_data_dir()` is invoked. It's called multiple times per run (model resolution, voice listing, downloads). A `@functools.lru_cache` would eliminate redundant syscalls.

Note: caching requires tests to clear the cache via monkeypatch — evaluate tradeoff.

---

### C6. `_default_play_cmd()` re-detects platform and probes `shutil.which` on every call
**File:** `reed.py:320-343`
**Severity:** Low (performance)

Called once per `speak_text` invocation. In blocking file mode, that's once per page/chapter. Caching would help for long PDFs.

---

### C7. `_playback_worker` swallows piper errors
**File:** `reed.py:122-124`
**Severity:** Low (UX)

When piper exits non-zero (but not due to stop), the worker prints `✗ Piper error` and returns silently. State transitions to IDLE via the finally block. There's no way for the caller (interactive loop) to know that generation failed — no callback, no state like `PlaybackState.ERROR`.

Not blocking for current usage (user sees the error message), but worth noting for future.

---

## 📐 Architecture Observations

### A1. `main()` is 220+ lines with multiple responsibilities
The function handles: arg parsing, model resolution, subcommands (voices, download), config creation, model downloading, interactive routing, PDF reading, EPUB reading (with skip logic), plain text reading. Consider extracting subcommand handlers.

### A2. Stale ARCHITECTURE.md reference
ARCHITECTURE.md line 162 mentions `_stop_requested` flag but code uses `_stop_event` (a `threading.Event`). Minor doc drift.

---

## ✅ Things Done Well

- **Dependency injection everywhere** — `run`, `print_fn`, `prompt_fn`, `clear_fn` make everything testable without mocking globals
- **127 tests with 0.12s runtime** — fast, comprehensive test suite
- **Clean separation** — `PlaybackController` is well-isolated with proper thread safety
- **Cross-platform support** — clean fallback chains for audio and clipboard
- **Rich UI** — good use of panels, tables, spinners without over-engineering
- **Monolithic-but-organized** — single file is a valid choice for CLI tools, and the code is well-sectioned
