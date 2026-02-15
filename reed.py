#!/usr/bin/env python3
"""reed - A CLI that reads text aloud using piper-tts."""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, TextIO

if TYPE_CHECKING:
    from prompt_toolkit import PromptSession

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


class ReedError(Exception):
    pass


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


def _download_file(url: str, dest: Path, print_fn: Callable = console.print) -> None:
    print_fn(f"[bold cyan]⬇ Downloading[/bold cyan] {escape(dest.name)}…")
    urllib.request.urlretrieve(url, dest)
    print_fn(f"[bold green]✓ Saved[/bold green] {escape(str(dest))}")


@dataclass(frozen=True)
class ReedConfig:
    model: Path = DEFAULT_MODEL
    speed: float = 1.0
    volume: float = 1.0
    silence: float = 0.6
    output: Optional[Path] = None


def ensure_model(config: ReedConfig, print_fn: Callable = console.print) -> None:
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
    if platform.system() == "Darwin":
        return ["afplay"]
    if platform.system() == "Linux":
        for cmd, args in [
            ("paplay", []),
            ("aplay", []),
            ("ffplay", ["-nodisp", "-autoexit"]),
        ]:
            if shutil.which(cmd):
                return [cmd, *args]
    raise ReedError("No supported audio player found")


def _default_clipboard_cmd() -> list[str]:
    if platform.system() == "Darwin":
        return ["pbpaste"]
    if platform.system() == "Linux":
        for cmd, args in [
            ("wl-paste", []),
            ("xclip", ["-selection", "clipboard", "-o"]),
            ("xsel", ["--clipboard", "--output"]),
        ]:
            if shutil.which(cmd):
                return [cmd, *args]
    raise ReedError("No supported clipboard tool found")


def get_text(
    args: argparse.Namespace,
    stdin: TextIO,
    run: Callable = subprocess.run,
) -> str:
    if args.clipboard:
        clipboard_cmd = _default_clipboard_cmd()
        result = run(clipboard_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ReedError("Failed to read clipboard")
        return result.stdout.strip()

    if args.file:
        return Path(args.file).read_text()

    if not stdin.isatty():
        return stdin.read().strip()

    if args.text:
        return " ".join(args.text)

    raise ReedError("No input provided. Use --help for usage.")


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


def print_generation_progress(print_fn: Callable = console.print) -> None:
    print_fn("[bold cyan]⠋ Generating speech...[/bold cyan]")


def print_playback_progress(print_fn: Callable = console.print) -> None:
    print_fn("[bold green]▶ Playing...[/bold green]")


def print_saved_message(output: Path, print_fn: Callable = console.print) -> None:
    panel = Panel.fit(
        f"[bold green]✓ Successfully saved[/bold green]\n\n"
        f"[dim]File:[/dim] [cyan]{escape(str(output))}[/cyan]",
        title="[bold]Output Saved[/bold]",
        border_style="green",
    )
    print_fn(panel)


def print_error(message: str, print_fn: Callable = console.print) -> None:
    panel = Panel.fit(
        f"[bold red]{escape(message)}[/bold red]",
        title="[bold]Error[/bold]",
        border_style="red",
    )
    print_fn(panel)


def print_banner(print_fn: Callable = console.print) -> None:
    print_fn(Text.from_markup(BANNER_MARKUP))


def print_help(print_fn: Callable = console.print) -> None:
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
    run: Callable = subprocess.run,
    print_fn: Callable = console.print,
) -> None:
    if config.output:
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
    else:
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
            play_cmd = _default_play_cmd()
            result = run([*play_cmd, tmp.name])
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
    print_fn: Callable = console.print,
    prompt_fn: Optional[Callable[[], str]] = None,
    clear_fn: Callable = console.clear,
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

            if text.lower() in quit_set:
                return 0
            elif text.lower() == help_cmd:
                print_help(print_fn)
                print_fn("")
                continue
            elif text.lower() == clear_cmd:
                clear_fn()
                print_banner(print_fn)
                continue
            elif text.lower() == replay_cmd:
                if last_text:
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
    if args.text or args.file or args.clipboard:
        return False
    if stdin is not None and hasattr(stdin, "isatty") and stdin.isatty():
        return True
    return False


def main(
    argv: Optional[list[str]] = None,
    run: Callable = subprocess.run,
    interactive_loop_fn: Optional[Callable] = None,
    stdin: Optional[TextIO] = None,
    print_fn: Callable = console.print,
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
        default=0.6,
        help="Seconds of silence between sentences",
    )
    args = parser.parse_args(argv)

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

    if _should_enter_interactive(args, stdin):
        try:
            ensure_model(config, print_fn)
        except ReedError as e:
            print_error(str(e), print_fn)
            return 1
        loop_fn = interactive_loop_fn or interactive_loop
        code = loop_fn(
            speak_line=lambda line: speak_text(
                line, config, run=run, print_fn=print_fn
            ),
            print_fn=print_fn,
        )
        return code

    try:
        assert stdin is not None
        text = get_text(args, stdin, run=run)

        if not text:
            print_error("No text to read.", print_fn)
            return 1

        ensure_model(config, print_fn)
        speak_text(text, config, run=run, print_fn=print_fn)
    except ReedError as e:
        print_error(str(e), print_fn)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
