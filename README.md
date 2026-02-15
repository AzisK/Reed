# reed

A CLI that reads text aloud using [piper-tts](https://github.com/rhasspy/piper). Uses the `en_US-kristin-medium` voice by default (auto-downloaded on first run).

## Features

- **Multiple input sources** — text argument, file (`-f`), clipboard (`-c`), or stdin
- **Pipe-friendly** — reads from stdin, works anywhere in a shell pipeline
- **Interactive mode** — conversational TTS with `/replay`, `/help`, `/clear`, tab completion, and history
- **Adjustable speech** — control speed (`-s`), volume (`-v`), and sentence silence (`--silence`)
- **Voice management** — download, list, and switch voices (`reed download`, `reed voices`, `-m`)
- **Swappable voices** — use any piper-tts `.onnx` model with `-m`
- **WAV export** — save output to file with `-o` instead of playing
- **Rich terminal UI** — styled output with progress indicators and error panels

## Requirements

- Python 3.14+
- macOS or Linux
  - **macOS**: `afplay` (audio), `pbpaste` (clipboard) — included with the OS
  - **Linux**: one of `paplay`, `aplay`, or `ffplay` (audio); one of `wl-paste`, `xclip`, or `xsel` (clipboard)
- [uv](https://docs.astral.sh/uv/) (for dependency management)
- Rich library for beautiful terminal UI

## Setup

```bash
uv venv
uv pip install -e .
```

### Voice Management

Voices are stored in `~/.local/share/reed/` (Linux/macOS, respects `XDG_DATA_HOME`) or `%LOCALAPPDATA%\reed\` (Windows).

The default voice (`en_US-kristin-medium`) is auto-downloaded on first run.

```bash
# Download a voice
reed download en_US-amy-medium

# List installed voices
reed voices

# Use a specific voice by name
reed -m en_US-amy-medium "Hello world"

# Or use a custom .onnx file by path
reed -m /path/to/custom-voice.onnx "Hello world"
```

All voice models are hosted on Hugging Face: [https://huggingface.co/rhasspy/piper-voices/tree/main](https://huggingface.co/rhasspy/piper-voices/tree/main)

## Usage

```bash
# Read text directly
reed "Hello, I will read this for you"

# Read from a file
reed -f article.txt

# Read from clipboard
reed -c

# Add longer silence between sentences (in seconds) while the default is 0.6 seconds
reed --silence 1 "First sentence. Second sentence. Bye bye."

# Interactive mode (launches automatically when no input is provided)
reed

# Interactive mode with longer silence (1 s) between sentences
reed --silence 1

# Save to WAV file instead of playing
reed -o output.wav "Save this"

# Play a saved WAV file
afplay output.wav

# Adjust speed (lower = slower) and volume
reed -s 0.8 -v 1.5 "Slower and louder"

# Combine speed, volume, and silence
reed -s 0.7 -v 1.3 --silence 0.3 -f long_article.txt
```

## Piped Usage

```bash
# Read from a file (alternative)
cat article.txt | reed

# Read from echo
echo 'Done, done' | reed

# Read from clipboard (alternative)
pbpaste | reed

# Read files in a directory
ls -1 | reed

# Read .txt files in a directory recursively
find . -name "*.txt" | reed

# Read the information about the disk usage
df -h | reed

# Save piped text to WAV and play it
echo "Notification" | reed -o /tmp/notify.wav && afplay /tmp/notify.wav

# Read git log
git log --oneline -5 | reed

# Read the content of a webpage, requires soffice (LibreOffice CLI)
# It can be found in the LibreOffice app directory and you can add an alias to it
# alias soffice='/Applications/LibreOffice.app/Contents/MacOS/soffice' inside `~/.zprofile` (~/.zshrc, ~/.bashrc etc.)
curl -s https://example.com -o /tmp/page.html && \
  soffice --headless --convert-to txt /tmp/page.html --outdir /tmp && \
  reed -f /tmp/page.txt
```

### Interactive mode

When launched with no arguments, reed enters interactive mode. Type or paste text and press Enter to hear it read aloud.

#### Commands

- Type text and press Enter to hear it
- Type `/quit` or `/exit` to stop
- Available commands in interactive mode: `/help`, `/clear`, `/replay`
- Press `Ctrl-D` for EOF to exit

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `-f`, `--file` | Read text from a file | — |
| `-c`, `--clipboard` | Read text from clipboard | — |
| `-m`, `--model` | Voice name or path to voice model | `en_US-kristin-medium` |
| `-s`, `--speed` | Speech speed (lower = slower) | `1.0` |
| `-v`, `--volume` | Volume multiplier | `1.0` |
| `-o`, `--output` | Save to WAV file instead of playing | — |
| `--silence` | Seconds of silence between sentences | `0.6` |

### Add to PATH

```bash
ln -s "$(pwd)/.venv/bin/reed" ~/.local/bin/reed
```
