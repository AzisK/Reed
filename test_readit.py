#!/usr/bin/env python3
"""Tests for readit interactive mode and core functions (TDD)."""

import io
import sys
import types
import argparse
from pathlib import Path


import importlib.util
import importlib.machinery
import pytest

_readit_path = str(Path(__file__).parent / "readit")
_loader = importlib.machinery.SourceFileLoader("readit", _readit_path)
_spec = importlib.util.spec_from_loader("readit", _loader, origin=_readit_path)
assert _spec
_readit = importlib.util.module_from_spec(_spec)
_readit.__file__ = _readit_path
_loader.exec_module(_readit)
sys.modules["readit"] = _readit


def _make_args(**overrides):
    defaults = dict(
        text=[],
        file=None,
        clipboard=False,
        model=Path(__file__).parent / "en_US-kristin-medium.onnx",
        speed=1.0,
        volume=1.0,
        output=None,
        silence=0.3,
        interactive=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_prompt_fn(lines: list[str]):
    """Create a prompt_fn that yields lines then raises EOFError."""
    it = iter(lines)
    def prompt_fn() -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError
    return prompt_fn


# ─── interactive_loop tests ───────────────────────────────────────────


class TestInteractiveLoop:
    def test_speaks_each_line_immediately(self):
        from readit import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["hello", "world", "/quit"]),
        )
        assert spoken == ["hello", "world"]
        assert result == 0

    def test_eof_exits_cleanly(self):
        from readit import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["hello"]),
        )
        assert spoken == ["hello"]
        assert result == 0

    def test_blank_lines_ignored(self):
        from readit import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["", "  ", "hello", "/quit"]),
        )
        assert spoken == ["hello"]
        assert result == 0

    def test_quit_commands_case_insensitive(self):
        from readit import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["Hello", "/EXIT"]),
        )
        assert spoken == ["Hello"]
        assert result == 0

    def test_exit_command(self):
        from readit import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["/exit"]),
        )
        assert spoken == []
        assert result == 0

    def test_colon_q_command(self):
        from readit import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn([":q"]),
        )
        assert spoken == []
        assert result == 0

    def test_multiline_paste_batched(self):
        from readit import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["line one\nline two\nline three", "/quit"]),
        )
        assert len(spoken) == 1
        assert "line one" in spoken[0]
        assert "line two" in spoken[0]
        assert "line three" in spoken[0]
        assert result == 0

    def test_ctrl_c_handled_gracefully(self):
        from readit import interactive_loop

        spoken: list[str] = []
        call_count = 0

        def raising_prompt() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "first"
            raise KeyboardInterrupt

        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=raising_prompt,
        )
        assert spoken == ["first"]
        assert result == 0

    def test_banner_printed(self):
        from readit import interactive_loop, BANNER_LINES

        stderr = io.StringIO()
        interactive_loop(
            speak_line=lambda t: None,
            stderr=stderr,
            prompt_fn=_make_prompt_fn(["/quit"]),
        )
        output = stderr.getvalue()
        for line in BANNER_LINES:
            assert line in output


# ─── build_piper_cmd tests ────────────────────────────────────────────


class TestBuildPiperCmd:
    def test_basic_command(self):
        from readit import build_piper_cmd

        cmd = build_piper_cmd(
            model=Path("/models/test.onnx"),
            speed=1.0,
            volume=1.0,
            silence=0.3,
            output=None,
        )
        assert cmd[1:3] == ["-m", "piper"]
        assert "--model" in cmd
        assert "/models/test.onnx" in cmd
        assert "--length-scale" in cmd
        assert "--volume" in cmd
        assert "--sentence-silence" in cmd

    def test_with_output_file(self):
        from readit import build_piper_cmd

        cmd = build_piper_cmd(
            model=Path("/models/test.onnx"),
            speed=1.0,
            volume=1.0,
            silence=0.3,
            output=Path("/out.wav"),
        )
        assert "--output-file" in cmd
        idx = cmd.index("--output-file")
        assert cmd[idx + 1] == "/out.wav"


# ─── speak_text tests ────────────────────────────────────────────────


class TestSpeakText:
    def test_play_path_calls_piper_then_afplay(self):
        from readit import speak_text

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return types.SimpleNamespace(returncode=0, stderr="")

        args = _make_args()
        speak_text("hi", args, run=fake_run)

        assert len(calls) == 2
        assert calls[0][0][1:3] == ["-m", "piper"]
        assert calls[0][1].get("input") == "hi"
        assert calls[1][0][0] == "afplay"

    def test_output_path_no_afplay(self):
        from readit import speak_text

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return types.SimpleNamespace(returncode=0, stderr="")

        stdout = io.StringIO()
        args = _make_args(output=Path("/tmp/out.wav"))
        speak_text("hi", args, run=fake_run, stdout=stdout)

        assert len(calls) == 1
        assert "Saved to" in stdout.getvalue()

    def test_piper_error_raises(self):
        from readit import speak_text, ReaditError

        def fake_run(cmd, **kwargs):
            return types.SimpleNamespace(returncode=1, stderr="boom")

        args = _make_args()
        with pytest.raises(ReaditError, match="boom"):
            speak_text("hi", args, run=fake_run)


# ─── main integration tests ──────────────────────────────────────────


class TestMainInteractiveFlag:
    def test_interactive_flag_routes_to_loop(self):
        from readit import main

        loop_called = []

        def fake_loop(**kwargs):
            loop_called.append(True)
            return 0

        code = main(
            argv=["-i"],
            interactive_loop_fn=fake_loop,
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
        )
        assert loop_called
        assert code == 0

    def test_no_input_defaults_to_interactive(self):
        from readit import main

        loop_called = []

        class FakeTtyStdin:
            def isatty(self):
                return True

            def readline(self):
                return ""

            def fileno(self):
                raise io.UnsupportedOperation("no fileno")

        def fake_loop(**kwargs):
            loop_called.append(True)
            return 0

        code = main(
            argv=[],
            interactive_loop_fn=fake_loop,
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=FakeTtyStdin(),
        )
        assert loop_called
        assert code == 0


# ─── _should_enter_interactive tests ─────────────────────────────────


class TestShouldEnterInteractive:
    def test_interactive_flag_true(self):
        from readit import _should_enter_interactive

        args = _make_args(interactive=True)
        assert _should_enter_interactive(args, io.StringIO()) is True

    def test_text_provided(self):
        from readit import _should_enter_interactive

        args = _make_args(text=["hello"])
        assert _should_enter_interactive(args, io.StringIO()) is False

    def test_file_provided(self):
        from readit import _should_enter_interactive

        args = _make_args(file="/tmp/test.txt")
        assert _should_enter_interactive(args, io.StringIO()) is False

    def test_clipboard(self):
        from readit import _should_enter_interactive

        args = _make_args(clipboard=True)
        assert _should_enter_interactive(args, io.StringIO()) is False

    def test_tty_stdin_no_args(self):
        from readit import _should_enter_interactive

        class FakeTty:
            def isatty(self):
                return True

        args = _make_args()
        assert _should_enter_interactive(args, FakeTty()) is True

    def test_non_tty_stdin_no_args(self):
        from readit import _should_enter_interactive

        args = _make_args()
        assert _should_enter_interactive(args, io.StringIO()) is False


# ─── get_text with stdin injection tests ─────────────────────────────


class TestGetTextStdin:
    def test_piped_stdin_read(self):
        from readit import get_text

        stdin = io.StringIO("hello from pipe")
        args = _make_args()
        result = get_text(args, stdin=stdin)
        assert result == "hello from pipe"
