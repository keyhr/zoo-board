# zoo-board

Turn your keyboard into a zoo.
A macOS tool that plays a random animal sound on every keystroke.
Built for chaos, it layers multiple sounds per keystroke by default. 21 animals included.

Sounds are decoded into memory once and mixed through a single, always-open
audio stream, so a keystroke turns into sound within a few milliseconds instead
of launching a new player process each time.

## Requirements

- macOS (uses `afplay`)
- Python 3
- `ffmpeg` (only needed if you want to (re-)fetch or process the sounds)

## Setup

```sh
git clone <repo-url>
cd zoo-board
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

The playback sounds in `sounds/` are bundled with the repository, so no fetching is required.

## Usage

```sh
./run.sh
```

- **Quit**: `Ctrl+C`
- Once running, keystrokes trigger sounds in any app (global monitoring)

### Options (tuning the chaos)

| Option | Default | Description |
| --- | --- | --- |
| `-n, --sounds-per-key N` | 3 | Max number of sounds layered per keystroke. Higher means more chaos |
| `-v, --volume V` | 1.0 | Volume (`afplay -v`; values above 1.0 amplify) |
| `-m, --max-concurrent N` | 32 | Cap on concurrent plays (runaway safeguard) |
| `--allow-repeat` | off | Also play on key-hold auto-repeat |
| `--legacy-afplay` | off | Force the old `afplay` backend (one process per keystroke; higher latency) |

Example (maximum chaos): `./run.sh -n 6 -v 1.5 --allow-repeat`

## Playback backend

By default playback uses a low-latency, in-process mixer built on
`sounddevice`, `numpy`, and `soundfile` (installed via `requirements.txt`).
All sounds are decoded once at startup, and the audio output stream stays open
for the whole session; a keystroke only appends samples to the mixer.

If those libraries are unavailable, or when `--legacy-afplay` is passed, the
tool falls back to spawning one `afplay` process per keystroke. That path needs
no extra Python packages but adds noticeable latency, because each keystroke
re-initialises the audio pipeline from scratch. `ffmpeg` is not required at
runtime by either backend.

## macOS permission (required)

Global key input monitoring requires the "Input Monitoring" permission.
On first run, you will be prompted to grant access to the terminal app you launched the tool from (Terminal, iTerm, etc.). Without it, keystrokes produce no sound.

- System Settings → Privacy & Security → Input Monitoring → turn ON your terminal app

## License

- **Code**: MIT ([LICENSE](LICENSE))
- **Sounds**: Public domain / CC0 / CC BY-SA, per file. See
  [ATTRIBUTIONS.md](ATTRIBUTIONS.md) for authors, sources, and licenses. The CC BY-SA
  sounds are distributed under the same terms. `gorilla` is an original synthesized sound
  made for this project.
