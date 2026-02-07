#!/usr/bin/env python3
"""readit - A CLI that reads text aloud using piper-tts."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, TextIO

if TYPE_CHECKING:
    from prompt_toolkit import PromptSession

DEFAULT_MODEL = Path(__file__).parent / "en_US-kristin-medium.onnx"

QUIT_WORDS = ("/quit", "/exit", ":q")

BANNER_LINES = (
    "Interactive mode. Type or paste text and press Enter.",
    "Type '/quit', '/exit', or ':q' to stop. Ctrl-D for EOF.",
)


class ReaditError(Exception):
    pass


def get_text(args: argparse.Namespace, stdin: TextIO) -> str:
    if args.clipboard:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
        if result.returncode != 0:
            raise ReaditError("Failed to read clipboard")
        return result.stdout.strip()

    if args.file:
        return Path(args.file).read_text()

    if not stdin.isatty():
        return stdin.read().strip()

    if args.text:
        return " ".join(args.text)

    raise ReaditError("No input provided. Use --help for usage.")


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


def speak_text(
    text: str,
    args: argparse.Namespace,
    run: Callable = subprocess.run,
    stdout: TextIO = sys.stdout,
) -> None:
    if args.output:
        piper_cmd = build_piper_cmd(
            args.model, args.speed, args.volume, args.silence, args.output
        )
        proc = run(piper_cmd, input=text, text=True, capture_output=True)
        if proc.returncode != 0:
            raise ReaditError(f"piper error: {proc.stderr}")
        print(f"Saved to {args.output}", file=stdout)
    else:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            piper_cmd = build_piper_cmd(
                args.model, args.speed, args.volume, args.silence, Path(tmp.name)
            )
            proc = run(piper_cmd, input=text, text=True, capture_output=True)
            if proc.returncode != 0:
                raise ReaditError(f"piper error: {proc.stderr}")
            result = run(["afplay", tmp.name])
            if result.returncode != 0:
                raise ReaditError("afplay error")


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
    stderr: TextIO = sys.stderr,
    prompt_fn: Optional[Callable[[], str]] = None,
) -> int:
    quit_set = {w.lower() for w in quit_words}

    for line in BANNER_LINES:
        print(line, file=stderr)

    if prompt_fn is None:
        session = _make_prompt_session(prompt, quit_words)
        prompt_fn = session.prompt

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
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue
            speak_line("\n".join(lines))
    except KeyboardInterrupt:
        return 0


def _should_enter_interactive(args: argparse.Namespace, stdin: TextIO) -> bool:
    if args.interactive:
        return True
    if args.text or args.file or args.clipboard:
        return False
    if hasattr(stdin, "isatty") and stdin.isatty():
        return True
    return False


def main(
    argv: Optional[list[str]] = None,
    run: Callable = subprocess.run,
    interactive_loop_fn: Optional[Callable] = None,
    stdin: Optional[TextIO] = None,
) -> int:
    if stdin is None:
        stdin = sys.stdin

    parser = argparse.ArgumentParser(
        prog="readit",
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
        default=0.3,
        help="Seconds of silence between sentences",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactive mode: type/paste text to read",
    )

    args = parser.parse_args(argv)

    if _should_enter_interactive(args, stdin):
        if not args.model.exists():
            print(f"Model not found: {args.model}", file=sys.stderr)
            return 1
        loop_fn = interactive_loop_fn or interactive_loop
        code = loop_fn(speak_line=lambda line: speak_text(line, args, run=run))
        return code

    try:
        text = get_text(args, stdin)

        if not text:
            print("No text to read.", file=sys.stderr)
            return 1

        if not args.model.exists():
            print(f"Model not found: {args.model}", file=sys.stderr)
            return 1

        speak_text(text, args, run=run)
    except ReaditError as e:
        print(str(e), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
