# reed

A CLI that reads text aloud using [piper-tts](https://github.com/rhasspy/piper). Uses the `en_US-kristin-medium` voice by default.

## Features

- **Multiple input sources** — text argument, file (`-f`), clipboard (`-c`), or stdin
- **Pipe-friendly** — reads from stdin, works anywhere in a shell pipeline
- **Interactive mode** — conversational TTS with `/replay`, `/help`, `/clear`, tab completion, and history
- **Adjustable speech** — control speed (`-s`), volume (`-v`), and sentence silence (`--silence`)
- **Swappable voices** — use any piper-tts `.onnx` model with `-m`
- **WAV export** — save output to file with `-o` instead of playing
- **Rich terminal UI** — styled output with progress indicators and error panels

## Requirements

- Python 3.14+
- macOS (uses `afplay` for audio playback and `pbpaste` for clipboard)
- [uv](https://docs.astral.sh/uv/) (for dependency management)
- Rich library for beautiful terminal UI

## Setup

```bash
uv venv
uv pip install -e .
```

Download a voice model and place the `.onnx` and `.onnx.json` files in the project root.

### Available Voice Models

All voice models are hosted on Hugging Face: [https://huggingface.co/rhasspy/piper-voices/tree/main](https://huggingface.co/rhasspy/piper-voices/tree/main)

The file structure follows this pattern: `language/COUNTRY/voice_name/quality/`

**Examples:**

- `en_US-kristin-medium.onnx` (default)
- `en_US-amy-medium.onnx`
- `en_GB-northern_english_male-medium.onnx`
- `de_DE-eva_k-xlow.onnx`

To download a model:

1. Navigate to the model directory on Hugging Face
2. Download the `.onnx` and `.onnx.json` files
3. Place them in the project root

To use a different voice, specify the model path:

```bash
reed -m en_US-amy-medium.onnx "Hello world"
```

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

# Interactive mode with silence longer between sentences
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
# It can be found in the LibreOffice installation directory and you can add an alias to it
# alias soffice='/Applications/LibreOffice.app/Contents/MacOS/soffice' inside `~/.zprofile` (~/.zshrc, ~/.bashrc etc.)
curl -s https://example.com -o /tmp/page.html && \
  soffice --headless --convert-to txt /tmp/page.html --outdir /tmp && \
  reed -f /tmp/page.txt
```

### Interactive mode

When launched with no arguments, reed enters interactive mode. Type or paste text and press Enter to hear it read aloud.

#### Visual Enhancements

- **Beautiful banner** with colors and icons
- **Spinner animation** while generating speech
- **Enhanced status messages** with panels and success indicators

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
| `-m`, `--model` | Path to voice model | `en_US-kristin-medium.onnx` |
| `-s`, `--speed` | Speech speed (lower = slower) | `1.0` |
| `-v`, `--volume` | Volume multiplier | `1.0` |
| `-o`, `--output` | Save to WAV file instead of playing | — |
| `--silence` | Seconds of silence between sentences | `0.6` |

### Add to PATH

```bash
ln -s "$(pwd)/.venv/bin/reed" ~/.local/bin/reed
```
