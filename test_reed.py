#!/usr/bin/env python3
"""Tests for reed interactive mode and core functions (TDD)."""

import argparse
import io
import types
from pathlib import Path

import pytest

import reed as _reed
from reed import ReedConfig


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
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_config(**overrides):
    defaults = dict(
        model=Path(__file__).parent / "en_US-kristin-medium.onnx",
        speed=1.0,
        volume=1.0,
        silence=0.3,
        output=None,
    )
    defaults.update(overrides)
    return ReedConfig(**defaults)


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
        from reed import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["hello", "world", "/quit"]),
        )
        assert spoken == ["hello", "world"]
        assert result == 0

    def test_eof_exits_cleanly(self):
        from reed import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["hello"]),
        )
        assert spoken == ["hello"]
        assert result == 0

    def test_blank_lines_ignored(self):
        from reed import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["", "  ", "hello", "/quit"]),
        )
        assert spoken == ["hello"]
        assert result == 0

    def test_quit_commands_case_insensitive(self):
        from reed import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["Hello", "/EXIT"]),
        )
        assert spoken == ["Hello"]
        assert result == 0

    def test_exit_command(self):
        from reed import interactive_loop

        spoken: list[str] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["/exit"]),
        )
        assert spoken == []
        assert result == 0

    def test_help_command(self):
        from reed import interactive_loop

        spoken: list[str] = []

        def print_fn(*args, **kwargs):
            None

        interactive_loop(
            speak_line=lambda t: spoken.append(t),
            print_fn=print_fn,
            prompt_fn=_make_prompt_fn(["/help", "/quit"]),
        )
        assert spoken == []

    def test_clear_command(self):
        from reed import interactive_loop

        spoken: list[str] = []
        cleared: list[bool] = []

        def print_fn(*args, **kwargs):
            None

        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            print_fn=print_fn,
            clear_fn=lambda: cleared.append(True),
            prompt_fn=_make_prompt_fn(["/clear", "/quit"]),
        )
        assert spoken == []
        assert cleared == [True]
        assert result == 0

    def test_replay_command(self):
        from reed import interactive_loop

        spoken: list[str] = []

        def print_fn(*args, **kwargs):
            None

        interactive_loop(
            speak_line=lambda t: spoken.append(t),
            print_fn=print_fn,
            prompt_fn=_make_prompt_fn(["first line", "/replay", "/quit"]),
        )
        assert len(spoken) == 2
        assert spoken[0] == spoken[1] == "first line"

    def test_replay_with_no_prior_text(self):
        from reed import interactive_loop

        spoken: list[str] = []
        printed: list[object] = []
        result = interactive_loop(
            speak_line=lambda t: spoken.append(t),
            print_fn=lambda *args, **kwargs: printed.append(args[0] if args else None),
            prompt_fn=_make_prompt_fn(["/replay", "/quit"]),
        )
        assert spoken == []
        assert any("No text to replay" in str(item) for item in printed)
        assert result == 0

    def test_multiline_paste_batched(self):
        from reed import interactive_loop

        spoken: list[str] = []
        interactive_loop(
            speak_line=lambda t: spoken.append(t),
            prompt_fn=_make_prompt_fn(["line one\nline two\nline three", "/quit"]),
        )
        assert len(spoken) == 1
        assert "line one" in spoken[0]
        assert "line two" in spoken[0]
        assert "line three" in spoken[0]

    def test_ctrl_c_handled_gracefully(self):
        from reed import interactive_loop

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
        from reed import interactive_loop

        printed: list[object] = []
        result = interactive_loop(
            speak_line=lambda t: None,
            print_fn=lambda *args, **kwargs: printed.append(args[0] if args else None),
            prompt_fn=_make_prompt_fn(["/quit"]),
        )
        assert result == 0
        assert any("reed" in str(item) for item in printed)


# ─── build_piper_cmd tests ────────────────────────────────────────────


class TestBuildPiperCmd:
    def test_basic_command(self):
        from reed import build_piper_cmd

        cmd = build_piper_cmd(
            model=Path("/models/test.onnx"),
            speed=1.0,
            volume=1.0,
            silence=0.3,
            output=None,
        )
        assert cmd[1:3] == ["-m", "piper"]
        assert "--model" in cmd
        assert str(Path("/models/test.onnx")) in cmd
        assert "--length-scale" in cmd
        assert "--volume" in cmd
        assert "--sentence-silence" in cmd

    def test_with_output_file(self):
        from reed import build_piper_cmd

        cmd = build_piper_cmd(
            model=Path("/models/test.onnx"),
            speed=1.0,
            volume=1.0,
            silence=0.3,
            output=Path("/out.wav"),
        )
        assert "--output-file" in cmd
        idx = cmd.index("--output-file")
        assert cmd[idx + 1] == str(Path("/out.wav"))


# ─── speak_text tests ────────────────────────────────────────────────


class TestSpeakText:
    def test_play_path_calls_piper_then_player(self, monkeypatch):
        from reed import _default_play_cmd, speak_text

        monkeypatch.setattr("reed.platform.system", lambda: "Darwin")

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return types.SimpleNamespace(returncode=0, stderr="")

        config = _make_config()
        speak_text("hi", config, run=fake_run)

        assert len(calls) == 2
        assert calls[0][0][1:3] == ["-m", "piper"]
        assert calls[0][1].get("input") == "hi"
        play_cmd = _default_play_cmd()
        assert calls[1][0][: len(play_cmd)] == play_cmd

    def test_output_path_no_afplay(self):
        from reed import speak_text

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return types.SimpleNamespace(returncode=0, stderr="")

        def print_fn(*args, **kwargs):
            None

        config = _make_config(output=Path("/tmp/out.wav"))
        speak_text("hi", config, run=fake_run, print_fn=print_fn)

        assert len(calls) == 1

    def test_piper_error_raises(self):
        from reed import ReedError, speak_text

        def fake_run(cmd, **kwargs):
            return types.SimpleNamespace(returncode=1, stderr="boom")

        config = _make_config()
        with pytest.raises(ReedError, match="boom"):
            speak_text("hi", config, run=fake_run)

    def test_playback_error_raises(self, monkeypatch):
        from reed import ReedError, speak_text

        monkeypatch.setattr("reed.platform.system", lambda: "Darwin")

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return types.SimpleNamespace(returncode=0, stderr="")
            return types.SimpleNamespace(returncode=1, stderr="")

        args = _make_args()
        with pytest.raises(ReedError, match="playback error"):
            speak_text("hi", args, run=fake_run)


# ─── main integration tests ──────────────────────────────────────────


class TestMainInteractiveFlag:
    def test_no_input_defaults_to_interactive(self):
        from reed import main

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
            argv=["-m", __file__],
            interactive_loop_fn=fake_loop,
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=FakeTtyStdin(),
        )
        assert loop_called
        assert code == 0


# ─── _should_enter_interactive tests ─────────────────────────────────


class TestShouldEnterInteractive:
    def test_text_provided(self):
        from reed import _should_enter_interactive

        args = _make_args(text=["hello"])
        assert _should_enter_interactive(args, io.StringIO()) is False

    def test_file_provided(self):
        from reed import _should_enter_interactive

        args = _make_args(file="/tmp/test.txt")
        assert _should_enter_interactive(args, io.StringIO()) is False

    def test_clipboard(self):
        from reed import _should_enter_interactive

        args = _make_args(clipboard=True)
        assert _should_enter_interactive(args, io.StringIO()) is False

    def test_tty_stdin_no_args(self):
        from reed import _should_enter_interactive

        class FakeTty:
            def isatty(self):
                return True

        args = _make_args()
        assert _should_enter_interactive(args, FakeTty()) is True

    def test_non_tty_stdin_no_args(self):
        from reed import _should_enter_interactive

        args = _make_args()
        assert _should_enter_interactive(args, io.StringIO()) is False

    def test_none_stdin(self):
        from reed import _should_enter_interactive

        args = _make_args()
        assert _should_enter_interactive(args, None) is False


# ─── _default_play_cmd tests ──────────────────────────────────────────


class TestDefaultPlayCmd:
    def test_macos_returns_afplay(self, monkeypatch):
        from reed import _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Darwin")
        assert _default_play_cmd() == ["afplay"]

    def test_linux_paplay(self, monkeypatch):
        from reed import _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            "reed.shutil.which",
            lambda cmd: "/usr/bin/paplay" if cmd == "paplay" else None,
        )
        assert _default_play_cmd() == ["paplay"]

    def test_linux_aplay_fallback(self, monkeypatch):
        from reed import _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            "reed.shutil.which",
            lambda cmd: "/usr/bin/aplay" if cmd == "aplay" else None,
        )
        assert _default_play_cmd() == ["aplay"]

    def test_linux_ffplay_fallback(self, monkeypatch):
        from reed import _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            "reed.shutil.which",
            lambda cmd: "/usr/bin/ffplay" if cmd == "ffplay" else None,
        )
        assert _default_play_cmd() == ["ffplay", "-nodisp", "-autoexit"]

    def test_linux_no_player_raises(self, monkeypatch):
        from reed import ReedError, _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr("reed.shutil.which", lambda cmd: None)
        with pytest.raises(ReedError, match="No supported audio player found"):
            _default_play_cmd()

    def test_unknown_platform_raises(self, monkeypatch):
        from reed import ReedError, _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Windows")
        with pytest.raises(ReedError, match="No supported audio player found"):
            _default_play_cmd()


# ─── _default_clipboard_cmd tests ────────────────────────────────────


class TestDefaultClipboardCmd:
    def test_macos_returns_pbpaste(self, monkeypatch):
        from reed import _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Darwin")
        assert _default_clipboard_cmd() == ["pbpaste"]

    def test_linux_wl_paste(self, monkeypatch):
        from reed import _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            "reed.shutil.which",
            lambda cmd: "/usr/bin/wl-paste" if cmd == "wl-paste" else None,
        )
        assert _default_clipboard_cmd() == ["wl-paste"]

    def test_linux_xclip_fallback(self, monkeypatch):
        from reed import _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            "reed.shutil.which",
            lambda cmd: "/usr/bin/xclip" if cmd == "xclip" else None,
        )
        assert _default_clipboard_cmd() == ["xclip", "-selection", "clipboard", "-o"]

    def test_linux_xsel_fallback(self, monkeypatch):
        from reed import _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr(
            "reed.shutil.which", lambda cmd: "/usr/bin/xsel" if cmd == "xsel" else None
        )
        assert _default_clipboard_cmd() == ["xsel", "--clipboard", "--output"]

    def test_linux_no_clipboard_raises(self, monkeypatch):
        from reed import ReedError, _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setattr("reed.shutil.which", lambda cmd: None)
        with pytest.raises(ReedError, match="No supported clipboard tool found"):
            _default_clipboard_cmd()

    def test_unknown_platform_raises(self, monkeypatch):
        from reed import ReedError, _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Windows")
        with pytest.raises(ReedError, match="No supported clipboard tool found"):
            _default_clipboard_cmd()


# ─── get_text clipboard with run injection test ──────────────────────


class TestGetTextClipboard:
    def test_clipboard_uses_injected_run(self, monkeypatch):
        from reed import get_text

        monkeypatch.setattr("reed.platform.system", lambda: "Darwin")

        def fake_run(cmd, **kwargs):
            return types.SimpleNamespace(
                returncode=0, stdout="clipboard text", stderr=""
            )

        class FakeTty:
            def isatty(self):
                return True

        args = _make_args(clipboard=True)
        result = get_text(args, stdin=FakeTty(), run=fake_run)
        assert result == "clipboard text"

    def test_clipboard_error_raises(self, monkeypatch):
        from reed import ReedError, get_text

        monkeypatch.setattr("reed.platform.system", lambda: "Darwin")

        def fake_run(cmd, **kwargs):
            return types.SimpleNamespace(returncode=1, stdout="", stderr="fail")

        class FakeTty:
            def isatty(self):
                return True

        args = _make_args(clipboard=True)
        with pytest.raises(ReedError, match="Failed to read clipboard"):
            get_text(args, stdin=FakeTty(), run=fake_run)


# ─── get_text with stdin injection tests ─────────────────────────────


class TestGetTextStdin:
    def test_piped_stdin_read(self):
        from reed import get_text

        stdin = io.StringIO("hello from pipe")
        args = _make_args()
        result = get_text(args, stdin=stdin)
        assert result == "hello from pipe"

    def test_text_args_joined(self):
        from reed import get_text

        class FakeTty:
            def isatty(self):
                return True

        args = _make_args(text=["hello", "world"])
        result = get_text(args, stdin=FakeTty())
        assert result == "hello world"


# ─── main error path tests ───────────────────────────────────────────


class TestMainErrors:
    def _capture_main(self, **kwargs):
        from rich.console import Console as RichConsole

        cap_console = RichConsole(file=io.StringIO(), force_terminal=False)
        code = _reed.main(print_fn=cap_console.print, **kwargs)
        output = cap_console.file.getvalue()
        return code, output

    def test_missing_model_returns_1(self):
        code, output = self._capture_main(
            argv=["-m", "/nonexistent/model.onnx"],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO("some text"),
        )
        assert code == 1
        assert "Model not found" in output

    def test_empty_text_returns_1(self):
        code, output = self._capture_main(
            argv=[],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 1

    def test_reed_error_returns_1(self):
        def failing_run(cmd, **kwargs):
            return types.SimpleNamespace(returncode=1, stderr="piper exploded")

        code, output = self._capture_main(
            argv=["-m", __file__],
            run=failing_run,
            stdin=io.StringIO("hello"),
        )
        assert code == 1
        assert "piper exploded" in output
