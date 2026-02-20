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
        pages=None,
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
    def test_no_input_defaults_to_interactive(self, monkeypatch):
        from reed import ReedError, main

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

        def no_player() -> list[str]:
            raise ReedError("No supported audio player found")

        monkeypatch.setattr("reed._default_play_cmd", no_player)

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

    def test_pages_provided(self):
        from reed import _should_enter_interactive

        class FakeTty:
            def isatty(self):
                return True

        args = _make_args(pages="1-2")
        assert _should_enter_interactive(args, FakeTty()) is False

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

    def test_windows_powershell(self, monkeypatch):
        from reed import _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Windows")
        monkeypatch.setattr(
            "reed.shutil.which",
            lambda cmd: (
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
                if cmd == "powershell"
                else None
            ),
        )
        result = _default_play_cmd()
        assert result[0] == "powershell"
        assert "-c" in result
        assert "System.Media.SoundPlayer" in " ".join(result)

    def test_windows_ffplay_fallback(self, monkeypatch):
        from reed import _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Windows")
        monkeypatch.setattr(
            "reed.shutil.which",
            lambda cmd: r"C:\ffmpeg\bin\ffplay.exe" if cmd == "ffplay" else None,
        )
        assert _default_play_cmd() == ["ffplay", "-nodisp", "-autoexit", "-hide_banner"]

    def test_windows_no_player_raises(self, monkeypatch):
        from reed import ReedError, _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Windows")
        monkeypatch.setattr("reed.shutil.which", lambda cmd: None)
        with pytest.raises(ReedError, match="No supported audio player found"):
            _default_play_cmd()

    def test_unknown_platform_raises(self, monkeypatch):
        from reed import ReedError, _default_play_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "FreeBSD")
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

    def test_windows_clipboard(self, monkeypatch):
        from reed import _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "Windows")
        assert _default_clipboard_cmd() == ["powershell", "-Command", "Get-Clipboard"]

    def test_unknown_platform_raises(self, monkeypatch):
        from reed import ReedError, _default_clipboard_cmd

        monkeypatch.setattr("reed.platform.system", lambda: "FreeBSD")
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


class TestIterPdfPages:
    def test_pdf_reads_all_pages_when_no_pages_flag(self, monkeypatch):
        from reed import _iter_pdf_pages

        class FakePage:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        class FakeReader:
            def __init__(self, path):
                self.pages = [FakePage("page one"), FakePage("page two")]

        monkeypatch.setattr("reed.PdfReader", FakeReader)

        result = list(_iter_pdf_pages(Path("book.pdf"), None))
        assert result == [(1, 2, "page one"), (2, 2, "page two")]

    def test_pdf_reads_selected_pages(self, monkeypatch):
        from reed import _iter_pdf_pages

        class FakePage:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        class FakeReader:
            def __init__(self, path):
                self.pages = [
                    FakePage("page one"),
                    FakePage("page two"),
                    FakePage("page three"),
                    FakePage("page four"),
                ]

        monkeypatch.setattr("reed.PdfReader", FakeReader)

        result = list(_iter_pdf_pages(Path("book.pdf"), "2,4"))
        assert result == [(2, 4, "page two"), (4, 4, "page four")]

    def test_pdf_page_out_of_bounds_raises(self, monkeypatch):
        from reed import ReedError, _iter_pdf_pages

        class FakePage:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        class FakeReader:
            def __init__(self, path):
                self.pages = [FakePage("page one"), FakePage("page two")]

        monkeypatch.setattr("reed.PdfReader", FakeReader)

        with pytest.raises(ReedError, match="out of range"):
            list(_iter_pdf_pages(Path("book.pdf"), "3"))

    def test_pdf_invalid_pages_format_raises(self, monkeypatch):
        from reed import ReedError, _iter_pdf_pages

        class FakePage:
            def __init__(self, text):
                self._text = text

            def extract_text(self):
                return self._text

        class FakeReader:
            def __init__(self, path):
                self.pages = [FakePage("page one"), FakePage("page two")]

        monkeypatch.setattr("reed.PdfReader", FakeReader)

        with pytest.raises(ReedError, match="Invalid page selection"):
            list(_iter_pdf_pages(Path("book.pdf"), "1,a"))

    def test_pages_flag_with_non_pdf_epub_file_raises(self):
        from reed import ReedError, get_text

        txt = io.StringIO("file content")
        args = _make_args(file="notes.txt", pages="1")
        with pytest.raises(ReedError, match="only be used with PDF or EPUB files"):
            get_text(args, stdin=txt)


# ─── _strip_html tests ───────────────────────────────────────────────


class TestStripHtml:
    def test_strips_basic_tags(self):
        from reed import _strip_html

        assert _strip_html(b"<p>Hello <b>world</b></p>") == "Hello world"

    def test_preserves_paragraph_breaks(self):
        from reed import _strip_html

        result = _strip_html(b"<p>First</p><p>Second</p>")
        assert result == "First\nSecond"

    def test_empty_input(self):
        from reed import _strip_html

        assert _strip_html(b"") == ""

    def test_plain_text_passthrough(self):
        from reed import _strip_html

        assert _strip_html(b"no tags here") == "no tags here"

    def test_handles_entities(self):
        from reed import _strip_html

        result = _strip_html(b"<p>A &amp; B</p>")
        assert "A & B" in result

    def test_block_elements_add_breaks(self):
        from reed import _strip_html

        result = _strip_html(b"<div>One</div><div>Two</div>")
        assert result == "One\nTwo"

    def test_br_adds_break(self):
        from reed import _strip_html

        result = _strip_html(b"Line one<br/>Line two")
        assert result == "Line one\nLine two"

    def test_headings_add_breaks(self):
        from reed import _strip_html

        result = _strip_html(b"<h1>Title</h1><p>Body text</p>")
        assert result == "Title\nBody text"


# ─── _split_paragraphs tests ─────────────────────────────────────────


class TestSplitParagraphs:
    def test_splits_on_blank_lines(self):
        from reed import _split_paragraphs

        result = _split_paragraphs("First paragraph.\n\nSecond paragraph.")
        assert result == ["First paragraph.", "Second paragraph."]

    def test_single_paragraph(self):
        from reed import _split_paragraphs

        result = _split_paragraphs("Just one line.")
        assert result == ["Just one line."]

    def test_each_line_separate(self):
        from reed import _split_paragraphs

        result = _split_paragraphs("Line one\nLine two\n\nLine three")
        assert result == ["Line one", "Line two", "Line three"]

    def test_empty_string(self):
        from reed import _split_paragraphs

        assert _split_paragraphs("") == []

    def test_only_whitespace(self):
        from reed import _split_paragraphs

        assert _split_paragraphs("  \n  \n  ") == []


# ─── _iter_epub_chapters tests ───────────────────────────────────────


class TestIterEpubChapters:
    def _fake_spine(self, html_list):
        """Create a fake spine: list of (href, FakeZf) from HTML byte strings."""

        class FakeZf:
            def __init__(self, data_map):
                self._data = data_map

            def read(self, href):
                return self._data[href]

        data = {f"ch{i}.xhtml": html for i, html in enumerate(html_list)}
        zf = FakeZf(data)
        return [(href, zf) for href in data]

    def test_reads_all_chapters(self, monkeypatch):
        from reed import _iter_epub_chapters

        spine = self._fake_spine([b"<p>Chapter one</p>", b"<p>Chapter two</p>"])
        monkeypatch.setattr("reed._load_epub_spine", lambda p: spine)

        result = list(_iter_epub_chapters(Path("book.epub"), None))
        assert len(result) == 2
        assert result[0] == (1, 2, "Chapter one")
        assert result[1] == (2, 2, "Chapter two")

    def test_selected_chapters(self, monkeypatch):
        from reed import _iter_epub_chapters

        spine = self._fake_spine(
            [b"<p>Ch one</p>", b"<p>Ch two</p>", b"<p>Ch three</p>", b"<p>Ch four</p>"]
        )
        monkeypatch.setattr("reed._load_epub_spine", lambda p: spine)

        result = list(_iter_epub_chapters(Path("book.epub"), "2,4"))
        assert result == [(2, 4, "Ch two"), (4, 4, "Ch four")]

    def test_chapter_out_of_range_raises(self, monkeypatch):
        from reed import ReedError, _iter_epub_chapters

        spine = self._fake_spine([b"<p>Only one</p>"])
        monkeypatch.setattr("reed._load_epub_spine", lambda p: spine)

        with pytest.raises(ReedError, match="Chapter 5 is out of range"):
            list(_iter_epub_chapters(Path("book.epub"), "5"))

    def test_yields_empty_chapters(self, monkeypatch):
        from reed import _iter_epub_chapters

        spine = self._fake_spine([b"<p>Has text</p>", b"  ", b"<p>Also text</p>"])
        monkeypatch.setattr("reed._load_epub_spine", lambda p: spine)

        result = list(_iter_epub_chapters(Path("book.epub"), None))
        assert len(result) == 3
        assert result[0] == (1, 3, "Has text")
        assert result[1] == (2, 3, "")
        assert result[2] == (3, 3, "Also text")

    def test_empty_text_still_yielded(self, monkeypatch):
        from reed import _iter_epub_chapters

        spine = self._fake_spine([b"  "])
        monkeypatch.setattr("reed._load_epub_spine", lambda p: spine)

        result = list(_iter_epub_chapters(Path("book.epub"), None))
        assert result == [(1, 1, "")]


# ─── main EPUB integration tests ────────────────────────────────────


class TestMainEpub:
    def _capture_main(self, **kwargs):
        from rich.console import Console as RichConsole

        cap_console = RichConsole(file=io.StringIO(), force_terminal=False)
        code = _reed.main(print_fn=cap_console.print, **kwargs)
        output = cap_console.file.getvalue()
        return code, output

    def _fake_spine(self, html_list):
        """Create a fake spine: list of (href, FakeZf) from HTML byte strings."""

        class FakeZf:
            def __init__(self, data_map):
                self._data = data_map

            def read(self, href):
                return self._data[href]

        data = {f"ch{i}.xhtml": html for i, html in enumerate(html_list)}
        zf = FakeZf(data)
        return [(href, zf) for href in data]

    def test_epub_file_reads_chapters(self, monkeypatch, tmp_path):
        epub_file = tmp_path / "book.epub"
        epub_file.touch()

        spoken: list[str] = []

        def fake_speak(text, config, *, run, print_fn, play_cmd):
            spoken.append(text)

        monkeypatch.setattr("reed.speak_text", fake_speak)
        monkeypatch.setattr(
            "reed._load_epub_spine",
            lambda p: self._fake_spine(
                [b"<p>Chapter one text</p>", b"<p>Chapter two text</p>"]
            ),
        )

        code, output = self._capture_main(
            argv=["-f", str(epub_file), "-m", __file__],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 0
        assert "Chapter 1/2" in output
        assert "Chapter one text" in spoken
        assert "Chapter two text" in spoken

    def test_epub_skips_to_next_chapter_with_text(self, monkeypatch, tmp_path):
        epub_file = tmp_path / "book.epub"
        epub_file.touch()

        spoken: list[str] = []

        def fake_speak(text, config, *, run, print_fn, play_cmd):
            spoken.append(text)

        monkeypatch.setattr("reed.speak_text", fake_speak)
        monkeypatch.setattr(
            "reed._load_epub_spine",
            lambda p: self._fake_spine([b"  ", b"<p>Real content</p>", b"  "]),
        )

        code, output = self._capture_main(
            argv=["-f", str(epub_file), "--pages", "1", "-m", __file__],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 0
        assert "has no text, skipping to chapter 2" in output
        assert "Chapter 2/3" in output
        assert spoken == ["Real content"]

    def test_epub_skip_no_subsequent_text(self, monkeypatch, tmp_path):
        epub_file = tmp_path / "book.epub"
        epub_file.touch()

        spoken: list[str] = []

        def fake_speak(text, config, *, run, print_fn, play_cmd):
            spoken.append(text)

        monkeypatch.setattr("reed.speak_text", fake_speak)
        monkeypatch.setattr(
            "reed._load_epub_spine",
            lambda p: self._fake_spine([b"<p>Content</p>", b"  "]),
        )

        code, output = self._capture_main(
            argv=["-f", str(epub_file), "--pages", "2", "-m", __file__],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 0
        assert "no subsequent chapter with text found" in output
        assert spoken == []

    def test_epub_all_chapters_skips_empty(self, monkeypatch, tmp_path):
        epub_file = tmp_path / "book.epub"
        epub_file.touch()

        spoken: list[str] = []

        def fake_speak(text, config, *, run, print_fn, play_cmd):
            spoken.append(text)

        monkeypatch.setattr("reed.speak_text", fake_speak)
        monkeypatch.setattr(
            "reed._load_epub_spine",
            lambda p: self._fake_spine([b"  ", b"<p>Real content</p>", b"  "]),
        )

        code, output = self._capture_main(
            argv=["-f", str(epub_file), "-m", __file__],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 0
        assert "Chapter 2/3" in output
        assert spoken == ["Real content"]

    def test_epub_speaks_paragraph_by_paragraph(self, monkeypatch, tmp_path):
        epub_file = tmp_path / "book.epub"
        epub_file.touch()

        spoken: list[str] = []

        def fake_speak(text, config, *, run, print_fn, play_cmd):
            spoken.append(text)

        monkeypatch.setattr("reed.speak_text", fake_speak)
        monkeypatch.setattr(
            "reed._load_epub_spine",
            lambda p: self._fake_spine(
                [b"<p>First paragraph.</p><p>Second paragraph.</p>"]
            ),
        )

        code, output = self._capture_main(
            argv=["-f", str(epub_file), "-m", __file__],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 0
        assert spoken == ["First paragraph.", "Second paragraph."]

    def test_pages_flag_works_with_epub(self, monkeypatch, tmp_path):
        epub_file = tmp_path / "book.epub"
        epub_file.touch()

        spoken: list[str] = []

        def fake_speak(text, config, *, run, print_fn, play_cmd):
            spoken.append(text)

        monkeypatch.setattr("reed.speak_text", fake_speak)
        monkeypatch.setattr(
            "reed._load_epub_spine",
            lambda p: self._fake_spine(
                [
                    b"<p>First chapter</p>",
                    b"<p>Second chapter</p>",
                    b"<p>Third chapter</p>",
                ]
            ),
        )

        code, output = self._capture_main(
            argv=["-f", str(epub_file), "--pages", "1,3", "-m", __file__],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 0
        assert spoken == ["First chapter", "Third chapter"]


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

    def test_empty_text_returns_1(self, monkeypatch):
        from reed import ReedError

        def no_player() -> list[str]:
            raise ReedError("No supported audio player found")

        monkeypatch.setattr("reed._default_play_cmd", no_player)

        code, output = self._capture_main(
            argv=[],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 1
        assert "No text to read." in output

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

    def test_pages_without_file_returns_1(self):
        code, output = self._capture_main(
            argv=["--pages", "1"],
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stderr=""),
            stdin=io.StringIO(""),
        )
        assert code == 1
        assert "--pages requires --file" in output


# ─── _data_dir tests ─────────────────────────────────────────────────


class TestDataDir:
    def test_linux_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr("reed.Path.home", lambda: tmp_path)
        d = _reed._data_dir()
        assert d == tmp_path / ".local" / "share" / "reed"
        assert d.is_dir()

    def test_linux_xdg(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed.platform.system", lambda: "Linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "custom"))
        d = _reed._data_dir()
        assert d == tmp_path / "custom" / "reed"
        assert d.is_dir()

    def test_macos_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed.platform.system", lambda: "Darwin")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr("reed.Path.home", lambda: tmp_path)
        d = _reed._data_dir()
        assert d == tmp_path / ".local" / "share" / "reed"

    def test_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed.platform.system", lambda: "Windows")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
        d = _reed._data_dir()
        assert d == tmp_path / "Local" / "reed"
        assert d.is_dir()


# ─── _model_url tests ────────────────────────────────────────────────


class TestModelUrl:
    def test_kristin(self):
        onnx, json_ = _reed._model_url("en_US-kristin-medium")
        assert onnx == (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "en/en_US/kristin/medium/en_US-kristin-medium.onnx"
        )
        assert json_ == (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "en/en_US/kristin/medium/en_US-kristin-medium.onnx.json"
        )

    def test_northern_english_male(self):
        onnx, json_ = _reed._model_url("en_GB-northern_english_male-medium")
        assert onnx == (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx"
        )
        assert json_ == (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json"
        )

    def test_de_DE_eva_k_x_low(self):
        onnx, json_ = _reed._model_url("de_DE-eva_k-x_low")
        assert onnx == (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "de/de_DE/eva_k/x_low/de_DE-eva_k-x_low.onnx"
        )
        assert json_ == (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "de/de_DE/eva_k/x_low/de_DE-eva_k-x_low.onnx.json"
        )


# ─── ensure_model tests ──────────────────────────────────────────────


class TestEnsureModel:
    def test_exists_is_noop(self, tmp_path):
        model = tmp_path / "test.onnx"
        model.touch()
        config = ReedConfig(model=model)
        _reed.ensure_model(config, print_fn=lambda *a, **k: None)

    def test_not_in_data_dir_raises(self, tmp_path):
        config = ReedConfig(model=tmp_path / "nonexistent.onnx")
        with pytest.raises(_reed.ReedError, match="Model not found"):
            _reed.ensure_model(config, print_fn=lambda *a, **k: None)

    def test_in_data_dir_downloads(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed._data_dir", lambda: tmp_path)
        model = tmp_path / "en_US-kristin-medium.onnx"
        config = ReedConfig(model=model)

        downloaded = []

        def fake_urlretrieve(url, dest):
            Path(dest).touch()
            downloaded.append((url, str(dest)))

        monkeypatch.setattr("reed.urllib.request.urlretrieve", fake_urlretrieve)
        _reed.ensure_model(config, print_fn=lambda *a, **k: None)
        assert len(downloaded) == 2
        assert model.exists()
        assert model.with_suffix(".onnx.json").exists()


# ─── list voices tests ───────────────────────────────────────────────


class TestListVoices:
    def _run_voices(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed._data_dir", lambda: tmp_path)
        from rich.console import Console as RichConsole

        cap_console = RichConsole(file=io.StringIO(), force_terminal=False)
        code = _reed.main(
            argv=["voices"],
            print_fn=cap_console.print,
            stdin=io.StringIO(""),
        )
        output = cap_console.file.getvalue()
        return code, output

    def test_empty_dir(self, monkeypatch, tmp_path):
        code, output = self._run_voices(monkeypatch, tmp_path)
        assert code == 0
        assert "No voices installed" in output

    def test_with_voices(self, monkeypatch, tmp_path):
        (tmp_path / "en_US-kristin-medium.onnx").write_bytes(b"\x00" * 1024)
        (tmp_path / "en_US-amy-medium.onnx").write_bytes(b"\x00" * 2048)
        monkeypatch.setattr("reed.DEFAULT_MODEL_NAME", "en_US-kristin-medium")
        code, output = self._run_voices(monkeypatch, tmp_path)
        assert code == 0
        assert "en_US-kristin-medium" in output
        assert "en_US-amy-medium" in output


# ─── download voice tests ────────────────────────────────────────────


class TestDownloadVoice:
    def test_download_both_files(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed._data_dir", lambda: tmp_path)
        downloaded = []

        def fake_urlretrieve(url, dest):
            Path(dest).touch()
            downloaded.append(url)

        monkeypatch.setattr("reed.urllib.request.urlretrieve", fake_urlretrieve)

        from rich.console import Console as RichConsole

        cap_console = RichConsole(file=io.StringIO(), force_terminal=False)
        code = _reed.main(
            argv=["download", "en_US-amy-medium"],
            print_fn=cap_console.print,
            stdin=io.StringIO(""),
        )
        assert code == 0
        assert len(downloaded) == 2
        assert any(".onnx.json" in u for u in downloaded)
        assert (tmp_path / "en_US-amy-medium.onnx").exists()


# ─── resolve model tests ─────────────────────────────────────────────


class TestResolveModel:
    def test_short_name_resolves_to_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed._data_dir", lambda: tmp_path)
        model_file = tmp_path / "en_US-amy-medium.onnx"
        model_file.touch()

        from rich.console import Console as RichConsole

        cap_console = RichConsole(file=io.StringIO(), force_terminal=False)

        def fake_run(cmd, **kwargs):
            return types.SimpleNamespace(returncode=0, stderr="")

        class FakeTty:
            def isatty(self):
                return True

        monkeypatch.setattr("reed._default_play_cmd", lambda: ["true"])

        code = _reed.main(
            argv=["-m", "en_US-amy-medium", "hello"],
            run=fake_run,
            print_fn=cap_console.print,
            stdin=FakeTty(),
        )
        assert code == 0

    def test_short_name_with_onnx_suffix(self, monkeypatch, tmp_path):
        monkeypatch.setattr("reed._data_dir", lambda: tmp_path)
        model_file = tmp_path / "en_US-amy-medium.onnx"
        model_file.touch()

        def fake_run(cmd, **kwargs):
            return types.SimpleNamespace(returncode=0, stderr="")

        class FakeTty:
            def isatty(self):
                return True

        monkeypatch.setattr("reed._default_play_cmd", lambda: ["true"])

        code = _reed.main(
            argv=["-m", "en_US-amy-medium.onnx", "hello"],
            run=fake_run,
            print_fn=lambda *a, **k: None,
            stdin=FakeTty(),
        )
        assert code == 0


# ─── PlaybackController tests ────────────────────────────────────────


class TestPlaybackState:
    def test_enum_values(self):
        from reed import PlaybackState

        assert PlaybackState.IDLE.value == 1
        assert PlaybackState.PLAYING.value == 2
        assert PlaybackState.PAUSED.value == 3
        assert PlaybackState.STOPPED.value == 4


class TestPlaybackController:
    def test_init_sets_idle_state(self):
        from reed import PlaybackController

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        assert controller.is_playing() is False

    def test_play_starts_background_thread(self, monkeypatch):
        from reed import PlaybackController, ReedConfig

        started = []

        def fake_thread(*args, **kwargs):
            started.append(True)
            # Don't actually start thread in test
            return types.SimpleNamespace(start=lambda: None)

        monkeypatch.setattr(_reed.threading, "Thread", fake_thread)

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        config = ReedConfig(model=Path("test.onnx"))
        controller.play("hello", config)

        assert len(started) == 1
        assert controller.get_current_text() == "hello"

    def test_stop_when_idle_returns_false(self):
        from reed import PlaybackController

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        result = controller.stop()
        assert result is False

    def test_pause_when_not_playing_returns_false(self):
        from reed import PlaybackController

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        result = controller.pause()
        assert result is False

    def test_resume_when_not_paused_returns_false(self):
        from reed import PlaybackController

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        result = controller.resume()
        assert result is False

    def test_pause_on_posix_sends_sigstop(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        sigstop = getattr(_reed.signal, "SIGSTOP", 9999)
        monkeypatch.setattr(_reed.signal, "SIGSTOP", sigstop, raising=False)

        signals_sent = []
        fake_proc = types.SimpleNamespace(
            send_signal=lambda sig: signals_sent.append(sig),
            poll=lambda: None,
        )

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PLAYING
        controller._current_proc = fake_proc
        controller._config = ReedConfig(model=Path("test.onnx"))

        monkeypatch.setattr("reed.os.name", "posix")

        result = controller.pause()

        assert result is True
        assert len(signals_sent) == 1
        assert signals_sent[0] == sigstop
        assert controller._state == PlaybackState.PAUSED

    def test_pause_on_windows_returns_false(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        fake_proc = types.SimpleNamespace()
        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PLAYING
        controller._current_proc = fake_proc
        controller._config = ReedConfig(model=Path("test.onnx"))

        monkeypatch.setattr("reed.os.name", "nt")

        result = controller.pause()

        assert result is False
        assert controller._state == PlaybackState.PLAYING

    def test_pause_on_posix_without_sigstop_returns_false(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        fake_proc = types.SimpleNamespace(
            send_signal=lambda sig: None, poll=lambda: None
        )
        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PLAYING
        controller._current_proc = fake_proc
        controller._config = ReedConfig(model=Path("test.onnx"))

        monkeypatch.setattr("reed.os.name", "posix")
        monkeypatch.delattr(_reed.signal, "SIGSTOP", raising=False)

        result = controller.pause()

        assert result is False
        assert controller._state == PlaybackState.PLAYING

    def test_resume_on_posix_sends_sigcont(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        sigcont = getattr(_reed.signal, "SIGCONT", 9998)
        monkeypatch.setattr(_reed.signal, "SIGCONT", sigcont, raising=False)

        signals_sent = []
        fake_proc = types.SimpleNamespace(
            send_signal=lambda sig: signals_sent.append(sig),
            poll=lambda: None,
        )

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PAUSED
        controller._current_proc = fake_proc
        controller._config = ReedConfig(model=Path("test.onnx"))

        monkeypatch.setattr("reed.os.name", "posix")

        result = controller.resume()

        assert result is True
        assert len(signals_sent) == 1
        assert signals_sent[0] == sigcont
        assert controller._state == PlaybackState.PLAYING

    def test_resume_on_windows_returns_false(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        fake_proc = types.SimpleNamespace()
        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PAUSED
        controller._current_proc = fake_proc
        controller._config = ReedConfig(model=Path("test.onnx"))

        monkeypatch.setattr("reed.os.name", "nt")

        result = controller.resume()

        assert result is False
        assert controller._state == PlaybackState.PAUSED

    def test_resume_on_posix_without_sigcont_returns_false(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        fake_proc = types.SimpleNamespace(
            send_signal=lambda sig: None, poll=lambda: None
        )
        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PAUSED
        controller._current_proc = fake_proc
        controller._config = ReedConfig(model=Path("test.onnx"))

        monkeypatch.setattr("reed.os.name", "posix")
        monkeypatch.delattr(_reed.signal, "SIGCONT", raising=False)

        result = controller.resume()

        assert result is False
        assert controller._state == PlaybackState.PAUSED

    def test_stop_terminates_processes(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        terminated = {"player": False, "piper": False}

        def fake_terminate_player():
            terminated["player"] = True

        def fake_terminate_piper():
            terminated["piper"] = True

        fake_player = types.SimpleNamespace(
            terminate=fake_terminate_player,
            wait=lambda timeout: None,
        )
        fake_piper = types.SimpleNamespace(
            terminate=fake_terminate_piper,
            poll=lambda: None,
        )

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PLAYING
        controller._current_proc = fake_player
        controller._piper_proc = fake_piper
        controller._config = ReedConfig(model=Path("test.onnx"))

        result = controller.stop()

        assert result is True
        assert terminated["player"] is True
        assert terminated["piper"] is True
        assert controller._state == PlaybackState.IDLE
        assert controller._current_proc is None
        assert controller._piper_proc is None

    def test_stop_handles_process_not_found(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        def fake_terminate():
            raise ProcessLookupError("No such process")

        def fake_kill():
            pass

        fake_player = types.SimpleNamespace(
            terminate=fake_terminate,
            wait=lambda timeout: (_ for _ in ()).throw(ProcessLookupError()),
            kill=fake_kill,
        )

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PLAYING
        controller._current_proc = fake_player
        controller._config = ReedConfig(model=Path("test.onnx"))

        result = controller.stop()

        assert result is True
        assert controller._state == PlaybackState.IDLE

    def test_stop_handles_timeout_then_kills(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig, subprocess

        wait_called = [0]

        def fake_wait(timeout):
            wait_called[0] += 1
            if wait_called[0] == 1:
                raise subprocess.TimeoutExpired(cmd="test", timeout=timeout)

        def fake_kill():
            pass

        fake_player = types.SimpleNamespace(
            terminate=lambda: None,
            wait=fake_wait,
            kill=fake_kill,
        )

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PLAYING
        controller._current_proc = fake_player
        controller._config = ReedConfig(model=Path("test.onnx"))

        result = controller.stop()

        assert result is True
        assert controller._state == PlaybackState.IDLE

    def test_get_current_text_returns_last_text(self):
        from reed import PlaybackController

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._current_text = "test text"
        assert controller.get_current_text() == "test text"

    def test_wait_joins_thread(self, monkeypatch):
        from reed import PlaybackController

        joined = []
        fake_thread = types.SimpleNamespace(join=lambda: joined.append(True))

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._playback_thread = fake_thread

        controller.wait()

        assert joined == [True]

    def test_wait_with_no_thread_does_nothing(self):
        from reed import PlaybackController

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._playback_thread = None
        controller.wait()  # Should not raise

    def test_play_stops_existing_before_starting(self, monkeypatch):
        from reed import PlaybackController, PlaybackState, ReedConfig

        stopped = []
        config = ReedConfig(model=Path("test.onnx"))

        controller = PlaybackController(print_fn=lambda *a, **k: None)
        controller._state = PlaybackState.PLAYING

        def fake_stop_locked():
            stopped.append(True)

        controller._stop_locked = fake_stop_locked

        controller.play("new text", config)

        assert stopped == [True]
        assert controller.get_current_text() == "new text"


# ─── speak_text with controller tests ────────────────────────────────


class TestSpeakTextWithController:
    def test_with_controller_uses_non_blocking_playback(self, monkeypatch):
        from reed import PlaybackController, ReedConfig, speak_text

        played_texts = []

        def fake_play(self, text, config):
            played_texts.append(text)

        monkeypatch.setattr(PlaybackController, "play", fake_play)

        config = ReedConfig(model=Path("test.onnx"))
        controller = PlaybackController(print_fn=lambda *a, **k: None)

        speak_text(
            "hello", config, print_fn=lambda *a, **k: None, controller=controller
        )

        assert played_texts == ["hello"]

    def test_with_controller_output_mode_still_blocking(self, monkeypatch):
        from reed import PlaybackController, ReedConfig, speak_text

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return types.SimpleNamespace(returncode=0, stderr="")

        config = ReedConfig(model=Path("test.onnx"), output=Path("/tmp/out.wav"))
        controller = PlaybackController(print_fn=lambda *a, **k: None)

        speak_text(
            "hello",
            config,
            run=fake_run,
            print_fn=lambda *a, **k: None,
            controller=controller,
        )

        # Should only call piper (not player), controller not used for output mode
        assert len(calls) == 1
        assert "--output-file" in calls[0]
