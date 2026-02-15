#!/usr/bin/env python3
"""reed - A CLI that reads text aloud using piper-tts."""

import argparse
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, TextIO

if TYPE_CHECKING:
    from prompt_toolkit import PromptSession

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

console = Console()


class ReedError(Exception):
    pass


DEFAULT_MODEL = Path(__file__).parent / "en_US-kristin-medium.onnx"


@dataclass(frozen=True)
class ReedConfig:
    model: Path = DEFAULT_MODEL
    speed: float = 1.0
    volume: float = 1.0
    silence: float = 0.6
    output: Optional[Path] = None


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


def get_text(args: argparse.Namespace, stdin: TextIO) -> str:
    if args.clipboard:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
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
            result = run(["afplay", tmp.name])
            if result.returncode != 0:
                raise ReedError("afplay error")
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
        "-m", "--model", type=Path, default=DEFAULT_MODEL, help="Path to voice model"
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

    config = ReedConfig(
        model=args.model,
        speed=args.speed,
        volume=args.volume,
        silence=args.silence,
        output=args.output,
    )

    if _should_enter_interactive(args, stdin):
        if not config.model.exists():
            print_error(f"Model not found: {config.model}", print_fn)
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
        text = get_text(args, stdin)

        if not text:
            print_error("No text to read.", print_fn)
            return 1

        if not config.model.exists():
            print_error(f"Model not found: {config.model}", print_fn)
            return 1

        speak_text(text, config, run=run, print_fn=print_fn)
    except ReedError as e:
        print_error(str(e), print_fn)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
