#!/usr/bin/env python3
"""reed - A CLI that reads text aloud using piper-tts."""

import argparse
import os
import platform
import shutil
import signal
import subprocess
from subprocess import CompletedProcess
import sys
import tempfile
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from enum import Enum, auto
from html.parser import HTMLParser
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, Optional, Sequence, TextIO

if TYPE_CHECKING:
    from prompt_toolkit import PromptSession

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - validated in runtime error path
    PdfReader = None  # type: ignore[assignment,misc]

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

DEFAULT_SILENCE = 0.6


class ReedError(Exception):
    pass


class PlaybackState(Enum):
    """Enum representing the current playback state."""

    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()


class PlaybackController:
    """Non-blocking playback controller for managing TTS audio playback.

    Runs piper TTS and audio player in a background thread, allowing
    pause/resume/stop controls without blocking the interactive prompt.
    """

    def __init__(self, print_fn: Callable[..., None] = console.print) -> None:
        self._current_proc: Optional[subprocess.Popen] = None
        self._piper_proc: Optional[subprocess.Popen] = None
        self._playback_thread: Optional[threading.Thread] = None
        self._state = PlaybackState.IDLE
        self._current_text = ""
        self._config: Optional[ReedConfig] = None
        self._lock = threading.Lock()
        self._print_fn = print_fn
        self._stop_requested = False

    def play(self, text: str, config: ReedConfig) -> None:
        """Start playback of text in a background thread.

        If already playing, stops current playback before starting new one.
        """
        with self._lock:
            if self._state == PlaybackState.PLAYING:
                self._stop_locked()
            self._current_text = text
            self._config = config
            self._state = PlaybackState.PLAYING
            self._stop_requested = False
            self._playback_thread = threading.Thread(
                target=self._playback_worker, args=(text, config), daemon=True
            )
            self._playback_thread.start()

    def _playback_worker(self, text: str, config: ReedConfig) -> None:
        """Background worker that generates and plays audio.

        Runs piper to generate WAV, then plays it with the system audio player.
        Uses Popen for both to enable pause/resume/stop controls.
        """
        play_cmd = _default_play_cmd()
        tmp_path = None

        try:
            # Generate WAV with piper
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            piper_cmd = build_piper_cmd(
                config.model,
                config.speed,
                config.volume,
                config.silence,
                Path(tmp_path),
            )
            self._piper_proc = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            piper_stdout, piper_stderr = self._piper_proc.communicate(
                input=text.encode("utf-8")
            )

            if self._stop_requested or self._piper_proc.returncode != 0:
                self._print_fn("\n[bold red]✗ Piper error[/bold red]")
                return

            # Play WAV with audio player
            self._current_proc = subprocess.Popen([*play_cmd, tmp_path])

            # Wait for playback to complete or be interrupted
            self._current_proc.wait()

            if self._stop_requested:
                self._state = PlaybackState.STOPPED
                self._print_fn("[bold red]⏹ Stopped[/bold red]")
            else:
                self._print_fn("[bold green]✓ Done[/bold green]")

        except Exception as e:
            self._print_fn(f"[bold red]Playback error: {e}[/bold red]")
        finally:
            # Cleanup temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            # Reset state if not stopped
            with self._lock:
                if self._state not in (PlaybackState.STOPPED, PlaybackState.PAUSED):
                    self._state = PlaybackState.IDLE
                self._current_proc = None
                self._piper_proc = None

    def pause(self) -> bool:
        """Pause playback. Returns True if successful.

        On Unix: sends SIGSTOP to player process.
        On Windows: not supported, returns False.
        """
        with self._lock:
            if self._state != PlaybackState.PLAYING or self._current_proc is None:
                return False
            if os.name == "posix":
                sigstop = getattr(signal, "SIGSTOP", None)
                if sigstop is None:
                    return False
                self._current_proc.send_signal(sigstop)
                self._state = PlaybackState.PAUSED
                self._print_fn("\n[bold yellow]⏸ Paused[/bold yellow]")
                return True
            return False

    def resume(self) -> bool:
        """Resume paused playback. Returns True if successful.

        On Unix: sends SIGCONT to player process.
        On Windows: not supported, returns False.
        """
        with self._lock:
            if self._state != PlaybackState.PAUSED or self._current_proc is None:
                return False
            if os.name == "posix":
                sigcont = getattr(signal, "SIGCONT", None)
                if sigcont is None:
                    return False
                self._current_proc.send_signal(sigcont)
                self._state = PlaybackState.PLAYING
                self._print_fn("\n[bold green]▶ Playing...[/bold green]")
                return True
            return False

    def stop(self) -> bool:
        """Stop playback. Returns True if was playing/paused."""
        with self._lock:
            return self._stop_locked()

    def _stop_locked(self) -> bool:
        """Internal stop implementation - must be called with lock held."""
        if self._state == PlaybackState.IDLE:
            return False

        self._stop_requested = True

        if self._current_proc:
            try:
                self._current_proc.terminate()
                self._current_proc.wait(timeout=2)
            except subprocess.TimeoutExpired, ProcessLookupError:
                try:
                    self._current_proc.kill()
                except ProcessLookupError:
                    pass

        if self._piper_proc and self._piper_proc.poll() is None:
            try:
                self._piper_proc.terminate()
            except ProcessLookupError:
                pass

        self._state = PlaybackState.IDLE
        self._current_proc = None
        self._piper_proc = None
        return True

    def is_playing(self) -> bool:
        """Check if currently playing."""
        with self._lock:
            return self._state == PlaybackState.PLAYING

    def wait(self) -> None:
        """Block until playback completes (for non-interactive mode)."""
        if self._playback_thread:
            self._playback_thread.join()

    def get_current_text(self) -> str:
        """Get the currently playing text (for replay)."""
        return self._current_text


def _data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "reed"
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULT_MODEL_NAME = "en_US-kristin-medium"
DEFAULT_MODEL = _data_dir() / f"{DEFAULT_MODEL_NAME}.onnx"


def _model_url(name: str) -> tuple[str, str]:
    parts = name.split("-")
    lang_code = parts[0]
    quality = parts[-1]
    voice_name = "_".join(parts[1:-1])
    family = lang_code[:2]
    base = (
        f"https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        f"{family}/{lang_code}/{voice_name}/{quality}/{name}"
    )
    return (f"{base}.onnx", f"{base}.onnx.json")


def _download_file(
    url: str, dest: Path, print_fn: Callable[..., None] = console.print
) -> None:
    print_fn(f"[bold cyan]⬇ Downloading[/bold cyan] {escape(dest.name)}…")
    urllib.request.urlretrieve(url, dest)
    print_fn(f"[bold green]✓ Saved[/bold green] {escape(str(dest))}")


@dataclass(frozen=True)
class ReedConfig:
    model: Path = DEFAULT_MODEL
    speed: float = 1.0
    volume: float = 1.0
    silence: float = DEFAULT_SILENCE
    output: Optional[Path] = None


def ensure_model(
    config: ReedConfig, print_fn: Callable[..., None] = console.print
) -> None:
    if config.model.exists():
        return
    if config.model.parent != _data_dir():
        raise ReedError(f"Model not found: {config.model}")
    name = config.model.stem
    onnx_url, json_url = _model_url(name)
    _download_file(onnx_url, config.model, print_fn)
    _download_file(json_url, config.model.with_suffix(".onnx.json"), print_fn)


QUIT_WORDS = ("/quit", "/exit")

BANNER_MARKUP = """🔊 [bold]reed[/bold] - Interactive Mode
──────────────────────────────────────────────────────────────
[dim]Type or paste text and press Enter to hear it.[/dim]
[dim]Type [bold]/quit[/bold] or [bold]/exit[/bold] to stop. Ctrl-D for EOF.[/dim]
[dim]Available commands: [bold]/help[/bold], [bold]/clear[/bold], [bold]/replay[/bold][/dim]"""

COMMANDS = {
    "/quit": "Exit interactive mode",
    "/exit": "Exit interactive mode (sync)",
    "/help": "Show this help",
    "/clear": "Clear screen",
    "/replay": "Replay last text",
}


def _default_play_cmd() -> list[str]:
    system = platform.system()
    if system == "Darwin":
        return ["afplay"]
    if system == "Linux":
        for cmd, args in [
            ("paplay", []),
            ("aplay", []),
            ("ffplay", ["-nodisp", "-autoexit"]),
        ]:
            if shutil.which(cmd):
                return [cmd, *args]
    if system == "Windows":
        if shutil.which("powershell"):
            return [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-c",
                "(New-Object System.Media.SoundPlayer $args[0]).PlaySync()",
            ]
        if shutil.which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-hide_banner"]
    raise ReedError("No supported audio player found")


def _default_clipboard_cmd() -> list[str]:
    system = platform.system()
    if system == "Darwin":
        return ["pbpaste"]
    if system == "Linux":
        for cmd, args in [
            ("wl-paste", []),
            ("xclip", ["-selection", "clipboard", "-o"]),
            ("xsel", ["--clipboard", "--output"]),
        ]:
            if shutil.which(cmd):
                return [cmd, *args]
    if system == "Windows":
        return ["powershell", "-Command", "Get-Clipboard"]
    raise ReedError("No supported clipboard tool found")


def get_text(
    args: argparse.Namespace,
    stdin: TextIO,
    run: Callable[..., CompletedProcess] = subprocess.run,
) -> str:
    if args.clipboard:
        clipboard_cmd = _default_clipboard_cmd()
        result = run(clipboard_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ReedError("Failed to read clipboard")
        return result.stdout.strip()

    if args.file:
        file_path = Path(args.file)
        if args.pages:
            raise ReedError("--pages can only be used with PDF or EPUB files")
        return file_path.read_text()

    if not stdin.isatty():
        return stdin.read().strip()

    if args.text:
        return " ".join(args.text)

    raise ReedError("No input provided. Use --help for usage.")


def _parse_range_selection(
    selection_str: str, total: int, label: str = "page"
) -> list[int]:
    selection = selection_str.strip()
    if not selection:
        raise ReedError("Invalid page selection")

    selected: list[int] = []
    seen: set[int] = set()
    for part in selection.split(","):
        token = part.strip()
        if not token:
            raise ReedError("Invalid page selection")

        if "-" in token:
            bounds = token.split("-", 1)
            if len(bounds) != 2 or not bounds[0].isdigit() or not bounds[1].isdigit():
                raise ReedError("Invalid page selection")
            start = int(bounds[0])
            end = int(bounds[1])
            if start < 1 or end < 1 or end < start:
                raise ReedError("Invalid page selection")
            pages: Sequence[int] = range(start, end + 1)
        else:
            if not token.isdigit():
                raise ReedError("Invalid page selection")
            page = int(token)
            if page < 1:
                raise ReedError("Invalid page selection")
            pages = [page]

        for page in pages:
            if page > total:
                raise ReedError(
                    f"{label.title()} {page} is out of range (total: {total})"
                )
            index = page - 1
            if index not in seen:
                seen.add(index)
                selected.append(index)

    if not selected:
        raise ReedError("Invalid page selection")
    return selected


def _iter_pdf_pages(
    path: Path, page_selection: Optional[str]
) -> Iterator[tuple[int, int, str]]:
    """Yield ``(page_number, total_pages, text)`` for each selected PDF page."""
    if PdfReader is None:
        raise ReedError("PDF support requires pypdf. Reinstall reed with dependencies.")

    try:
        reader = PdfReader(str(path))
    except Exception as e:  # pragma: no cover - depends on third-party parser internals
        raise ReedError(f"Failed to read PDF: {e}")

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ReedError("PDF has no pages")

    if page_selection:
        page_indices: Sequence[int] = _parse_range_selection(
            page_selection, total_pages
        )
    else:
        page_indices = range(total_pages)

    found_any = False
    for index in page_indices:
        page_text = reader.pages[index].extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            found_any = True
            yield (index + 1, total_pages, page_text)

    if not found_any:
        raise ReedError("No extractable text found in PDF")


_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "tr",
        "blockquote",
        "section",
        "article",
    }
)


class _HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML, stripping all tags."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        lines = raw.split("\n")
        paragraphs = [" ".join(line.split()) for line in lines]
        return "\n".join(paragraphs).strip()


def _strip_html(html_bytes: bytes) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(html_bytes.decode("utf-8", errors="replace"))
    return extractor.get_text()


def _load_epub_spine(path: Path) -> list[tuple[str, zipfile.ZipFile]]:
    """Parse EPUB spine and return ``(href, zip_file)`` pairs in reading order.

    Only reads the OPF manifest (lightweight), does NOT decompress chapter content.
    Each item is a tuple of ``(internal_path, ZipFile)`` so callers can lazily
    read individual chapters with ``zf.read(href)``.
    """
    try:
        zf = zipfile.ZipFile(str(path), "r")
    except Exception as e:
        raise ReedError(f"Failed to open EPUB: {e}")

    try:
        container_xml = zf.read("META-INF/container.xml")
    except KeyError:
        zf.close()
        raise ReedError("Invalid EPUB: missing META-INF/container.xml")

    container = ET.fromstring(container_xml)
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile_el = container.find(".//c:rootfile", ns)
    if rootfile_el is None:
        zf.close()
        raise ReedError("Invalid EPUB: no rootfile in container.xml")
    opf_path = rootfile_el.get("full-path", "")

    try:
        opf_xml = zf.read(opf_path)
    except KeyError:
        zf.close()
        raise ReedError(f"Invalid EPUB: missing {opf_path}")

    opf = ET.fromstring(opf_xml)
    opf_ns = opf.tag.split("}")[0] + "}" if "}" in opf.tag else ""
    opf_dir = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""

    manifest: dict[str, str] = {}
    for item in opf.findall(f".//{opf_ns}manifest/{opf_ns}item"):
        item_id = item.get("id", "")
        href = item.get("href", "")
        media = item.get("media-type", "")
        props = item.get("properties", "")
        if media == "application/xhtml+xml" and "nav" not in props:
            manifest[item_id] = opf_dir + href

    spine_hrefs: list[tuple[str, zipfile.ZipFile]] = []
    for itemref in opf.findall(f".//{opf_ns}spine/{opf_ns}itemref"):
        idref = itemref.get("idref", "")
        if idref in manifest:
            spine_hrefs.append((manifest[idref], zf))

    if not spine_hrefs:
        zf.close()
        raise ReedError("No chapters found in EPUB")

    return spine_hrefs


def _read_epub_chapter(chapter: tuple[str, zipfile.ZipFile]) -> str:
    """Read and strip HTML from a single EPUB chapter. Lightweight — only decompresses one file."""
    href, zf = chapter
    try:
        raw = zf.read(href)
    except KeyError:
        return ""
    return _strip_html(raw).strip()


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraph-sized chunks for incremental TTS.

    Each non-blank line becomes a separate chunk that is spoken individually
    so playback starts quickly.
    """
    return [line.strip() for line in text.splitlines() if line.strip()]


def _iter_epub_chapters(
    path: Path, chapter_selection: Optional[str]
) -> Iterator[tuple[int, int, str]]:
    """Yield ``(chapter_number, total_chapters, text)`` for each selected EPUB chapter."""
    chapters = _load_epub_spine(path)
    total_chapters = len(chapters)

    if chapter_selection:
        chapter_indices: Sequence[int] = _parse_range_selection(
            chapter_selection, total_chapters, label="chapter"
        )
    else:
        chapter_indices = range(total_chapters)

    for index in chapter_indices:
        text = _read_epub_chapter(chapters[index])
        yield (index + 1, total_chapters, text)


def build_piper_cmd(
    model: Path,
    speed: float,
    volume: float,
    silence: float,
    output: Optional[Path] = None,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "piper",
        "--model",
        str(model),
        "--length-scale",
        str(speed),
        "--volume",
        str(volume),
        "--sentence-silence",
        str(silence),
    ]
    if output:
        cmd += ["--output-file", str(output)]
    return cmd


def print_generation_progress(print_fn: Callable[..., None] = console.print) -> None:
    print_fn("[bold cyan]⠋ Generating speech...[/bold cyan]")


def print_playback_progress(print_fn: Callable[..., None] = console.print) -> None:
    print_fn("[bold green]▶ Playing...[/bold green]")


def print_saved_message(
    output: Path, print_fn: Callable[..., None] = console.print
) -> None:
    panel = Panel.fit(
        f"[bold green]✓ Successfully saved[/bold green]\n\n"
        f"[dim]File:[/dim] [cyan]{escape(str(output))}[/cyan]",
        title="[bold]Output Saved[/bold]",
        border_style="green",
    )
    print_fn(panel)


def print_error(message: str, print_fn: Callable[..., None] = console.print) -> None:
    panel = Panel.fit(
        f"[bold red]{escape(message)}[/bold red]",
        title="[bold]Error[/bold]",
        border_style="red",
    )
    print_fn(panel)


def print_banner(print_fn: Callable[..., None] = console.print) -> None:
    print_fn(Text.from_markup(BANNER_MARKUP))


def print_help(print_fn: Callable[..., None] = console.print) -> None:
    text = Text.from_markup("\n[bold]Available Commands:[/bold]\n")
    for cmd, desc in COMMANDS.items():
        cmd_text = Text(cmd)
        cmd_text.stylize("cyan")
        text.append(f"\n{cmd_text} - {desc}")
    panel = Panel(text, title="Commands", border_style="cyan")
    print_fn(panel)


def speak_text(
    text: str,
    config: ReedConfig,
    run: Callable[..., CompletedProcess] = subprocess.run,
    print_fn: Callable[..., None] = console.print,
    play_cmd: Optional[list[str]] = None,
    controller: Optional[PlaybackController] = None,
) -> None:
    """Speak text aloud.

    Args:
        text: Text to speak.
        config: Reed configuration.
        run: subprocess runner (for testing).
        print_fn: Function for printing messages.
        play_cmd: Audio player command (optional, auto-detected if None).
        controller: PlaybackController for non-blocking playback (optional).
                   If provided, playback is non-blocking. If None, blocks.
    """
    if config.output:
        # File output mode - always blocking
        print_generation_progress(print_fn)
        start = time.time()
        piper_cmd = build_piper_cmd(
            config.model, config.speed, config.volume, config.silence, config.output
        )
        proc = run(piper_cmd, input=text, text=True, capture_output=True)
        elapsed = time.time() - start
        if proc.returncode != 0:
            raise ReedError(f"piper error: {proc.stderr}")
        print_fn(f"\n[bold green]✓ Done in {elapsed:.1f}s[/bold green]")
        print_saved_message(config.output, print_fn)
    elif controller is not None:
        # Non-blocking mode with controller
        print_generation_progress(print_fn)
        controller.play(text, config)
    else:
        # Legacy blocking mode
        print_generation_progress(print_fn)
        start = time.time()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            piper_cmd = build_piper_cmd(
                config.model,
                config.speed,
                config.volume,
                config.silence,
                Path(tmp.name),
            )
            proc = run(piper_cmd, input=text, text=True, capture_output=True)
            if proc.returncode != 0:
                raise ReedError(f"piper error: {proc.stderr}")
            print_fn(
                f"\n[bold green]✓ Generated in {time.time() - start:.1f}s[/bold green]"
            )
            print_playback_progress(print_fn)
            resolved_play_cmd = play_cmd or _default_play_cmd()
            result = run([*resolved_play_cmd, tmp.name])
            if result.returncode != 0:
                raise ReedError("playback error")
            print_fn("[bold green]✓ Done[/bold green]")


def _make_prompt_session(
    prompt: str,
    quit_words: tuple[str, ...],
) -> "PromptSession[str]":
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import InMemoryHistory

    history = InMemoryHistory()
    for cmd in quit_words:
        history.append_string(cmd)

    return PromptSession(
        message=prompt,
        history=history,
        auto_suggest=AutoSuggestFromHistory(),
    )


def interactive_loop(
    speak_line: Callable[[str], None],
    prompt: str = "> ",
    quit_words: tuple[str, ...] = QUIT_WORDS,
    print_fn: Callable[..., None] = console.print,
    prompt_fn: Optional[Callable[[], str]] = None,
    clear_fn: Callable[..., None] = console.clear,
    controller: Optional[PlaybackController] = None,
) -> int:
    quit_set = {w.lower() for w in quit_words}
    help_cmd = "/help"
    clear_cmd = "/clear"
    replay_cmd = "/replay"

    print_banner(print_fn)

    if prompt_fn is None:
        session = _make_prompt_session(prompt, quit_words)
        prompt_fn = session.prompt

    last_text = ""

    try:
        while True:
            try:
                text = prompt_fn()
            except EOFError:
                return 0

            text = text.strip()
            if not text:
                continue

            cmd = text.lower()
            if cmd in quit_set:
                return 0
            elif cmd == help_cmd:
                print_help(print_fn)
                print_fn("")
                continue
            elif cmd == clear_cmd:
                clear_fn()
                print_banner(print_fn)
                continue
            elif cmd == replay_cmd:
                if controller is not None:
                    # Replay using controller's stored text
                    replay_text = controller.get_current_text()
                    if replay_text:
                        speak_line(replay_text)
                        print_fn("")
                    else:
                        print_fn("[bold yellow]No text to replay.[/bold yellow]\n")
                elif last_text:
                    speak_line(last_text)
                    print_fn("")
                else:
                    print_fn("[bold yellow]No text to replay.[/bold yellow]\n")
                continue

            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue
            last_text = "\n".join(lines)
            speak_line(last_text)
            print_fn("")
    except KeyboardInterrupt:
        return 0


def _should_enter_interactive(
    args: argparse.Namespace, stdin: Optional[TextIO]
) -> bool:
    if args.text or args.file or args.clipboard or args.pages:
        return False
    if stdin is not None and hasattr(stdin, "isatty") and stdin.isatty():
        return True
    return False


def main(
    argv: Optional[list[str]] = None,
    run: Callable[..., CompletedProcess] = subprocess.run,
    interactive_loop_fn: Optional[Callable[..., int]] = None,
    stdin: Optional[TextIO] = None,
    print_fn: Callable[..., None] = console.print,
) -> int:
    if stdin is None:
        stdin = sys.stdin

    parser = argparse.ArgumentParser(
        prog="reed",
        description="Read text aloud using piper-tts",
    )
    parser.add_argument("text", nargs="*", help="Text to read aloud")
    parser.add_argument("-f", "--file", help="Read text from a file")
    parser.add_argument(
        "--pages",
        default=None,
        help="PDF pages to read (1-based), e.g. 1,3-5",
    )
    parser.add_argument(
        "-c", "--clipboard", action="store_true", help="Read text from clipboard"
    )
    parser.add_argument(
        "-m", "--model", default=None, help="Voice name or path to voice model"
    )
    parser.add_argument(
        "-s",
        "--speed",
        type=float,
        default=1.0,
        help="Speech speed (default: 1.0, lower=slower)",
    )
    parser.add_argument(
        "-v",
        "--volume",
        type=float,
        default=1.0,
        help="Volume multiplier (default: 1.0)",
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="Save to WAV file instead of playing"
    )
    parser.add_argument(
        "--silence",
        type=float,
        default=DEFAULT_SILENCE,
        help="Seconds of silence between sentences",
    )
    args = parser.parse_args(argv)
    if args.pages:
        if not args.file:
            print_error("--pages requires --file <PDF or EPUB>", print_fn)
            return 1
        if Path(args.file).suffix.lower() not in (".pdf", ".epub"):
            print_error("--pages can only be used with PDF or EPUB files", print_fn)
            return 1

    # Resolve model: None → default, short name → data dir path
    if args.model is None:
        model_path = DEFAULT_MODEL
    else:
        model_path = Path(args.model)
        if not model_path.exists() and "/" not in args.model and "\\" not in args.model:
            name = args.model
            if not name.endswith(".onnx"):
                name += ".onnx"
            model_path = _data_dir() / name

    # ── reed voices ──────────────────────────────────────────────
    if args.text == ["voices"]:
        data = _data_dir()
        models = sorted(data.glob("*.onnx"))
        if not models:
            print_fn("[dim]No voices installed.[/dim]")
            print_fn(
                f"[dim]Download one with:[/dim] reed download {DEFAULT_MODEL_NAME}"
            )
            return 0
        table = Table(title="Installed Voices")
        table.add_column("Name", style="cyan")
        table.add_column("Size (MB)", justify="right")
        table.add_column("", justify="center")
        for m in models:
            star = "⭐" if m.stem == DEFAULT_MODEL_NAME else ""
            size_mb = f"{m.stat().st_size / 1_048_576:.1f}"
            table.add_row(m.stem, size_mb, star)
        print_fn(table)
        return 0

    # ── reed download <name> ─────────────────────────────────────
    if args.text and args.text[0] == "download":
        if len(args.text) < 2:
            print_error("Usage: reed download <voice-name>", print_fn)
            return 1
        name = args.text[1]
        if name.endswith(".onnx"):
            name = name[:-5]
        onnx_url, json_url = _model_url(name)
        dest = _data_dir() / f"{name}.onnx"
        try:
            _download_file(onnx_url, dest, print_fn)
            _download_file(json_url, dest.with_suffix(".onnx.json"), print_fn)
        except Exception as e:
            print_error(f"Download failed: {e}", print_fn)
            return 1
        print_fn(
            f'\n[bold green]✓ Voice ready![/bold green] Use with: reed -m {name} "Hello"'
        )
        return 0

    config = ReedConfig(
        model=model_path,
        speed=args.speed,
        volume=args.volume,
        silence=args.silence,
        output=args.output,
    )

    # Ensure model is available before any speaking mode
    try:
        ensure_model(config, print_fn)
    except ReedError as e:
        print_error(str(e), print_fn)
        return 1

    # Resolve playback command lazily in speak_text so non-playback flows
    # (e.g., empty input, mocked speak_text in tests) don't fail early.
    play_cmd = None

    if _should_enter_interactive(args, stdin):
        # Create controller for non-blocking interactive playback
        controller = PlaybackController(print_fn=print_fn)
        loop_fn = interactive_loop_fn or interactive_loop
        code = loop_fn(
            speak_line=lambda line: speak_text(
                line,
                config,
                run=run,
                print_fn=print_fn,
                play_cmd=play_cmd,
                controller=controller,
            ),
            print_fn=print_fn,
            controller=controller,
        )
        return code

    try:
        assert stdin is not None

        if args.file and Path(args.file).suffix.lower() == ".pdf":
            for page_num, total, page_text in _iter_pdf_pages(
                Path(args.file), args.pages
            ):
                print_fn(f"\n[bold cyan]📄 Page {page_num}/{total}[/bold cyan]")
                speak_text(
                    page_text, config, run=run, print_fn=print_fn, play_cmd=play_cmd
                )
            return 0

        if args.file and Path(args.file).suffix.lower() == ".epub":
            epub_path = Path(args.file)

            def _speak_chapter(ch_text: str) -> None:
                paragraphs = _split_paragraphs(ch_text)
                for para in paragraphs:
                    speak_text(
                        para, config, run=run, print_fn=print_fn, play_cmd=play_cmd
                    )

            chapters = _load_epub_spine(epub_path)
            total = len(chapters)
            spoken: set[int] = set()

            for ch_num, total_chapters, text in _iter_epub_chapters(
                epub_path, args.pages
            ):
                if ch_num in spoken:
                    continue
                if text:
                    spoken.add(ch_num)
                    print_fn(
                        f"\n[bold cyan]📖 Chapter {ch_num}/{total_chapters}[/bold cyan]"
                    )
                    _speak_chapter(text)
                    continue

                # Chapter is empty — skip to next chapter with text
                for next_index in range(ch_num, total):
                    next_num = next_index + 1
                    if next_num in spoken:
                        continue
                    next_text = _read_epub_chapter(chapters[next_index])
                    if next_text:
                        spoken.add(next_num)
                        print_fn(
                            f"\n[yellow]⏭ Chapter {ch_num}/{total_chapters} has no text, "
                            f"skipping to chapter {next_num}[/yellow]"
                        )
                        print_fn(
                            f"\n[bold cyan]📖 Chapter {next_num}/{total_chapters}[/bold cyan]"
                        )
                        _speak_chapter(next_text)
                        break
                else:
                    print_fn(
                        f"\n[yellow]⏭ Chapter {ch_num}/{total_chapters} has no text "
                        f"(no subsequent chapter with text found)[/yellow]"
                    )
            return 0

        text = get_text(args, stdin, run=run)

        if not text:
            print_error("No text to read.", print_fn)
            return 1

        speak_text(text, config, run=run, print_fn=print_fn, play_cmd=play_cmd)
    except ReedError as e:
        print_error(str(e), print_fn)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
