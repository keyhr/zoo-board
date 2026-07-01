#!/usr/bin/env python3
"""Play a random animal sound on every keystroke.

- Watches global key-press events via pynput.
- On each press, picks random sound(s) from sounds/ and plays them.
- Ignores key auto-repeat so that one physical keystroke maps to one trigger.

Playback backends
-----------------
By default a low-latency, in-process backend is used (StreamPlayer): all
sounds are decoded into memory once at startup and mixed into a single audio
output stream that stays open for the whole session. A keystroke only appends
samples to the mixer, so the sound starts on the next audio callback (a few
milliseconds) instead of paying the cost of launching a process and
initialising CoreAudio on every keystroke.

If the audio libraries (sounddevice / numpy / soundfile) are unavailable, or
with --legacy-afplay, playback falls back to spawning one `afplay` process per
keystroke. That path is simpler but adds noticeable latency because each
keystroke re-initialises the audio pipeline.

On macOS, global key monitoring requires the "Input Monitoring" permission.
The first run will ask you to grant it to the terminal app running this script
(Terminal / iTerm / etc.). Enable it under
System Settings > Privacy & Security > Input Monitoring.

Quit with Ctrl+C in the terminal.
"""
import argparse
import os
import random
import subprocess
import sys
import threading

SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
AUDIO_EXT = (".mp3", ".wav", ".aiff", ".aif", ".m4a", ".caf")


def load_sounds(directory):
    if not os.path.isdir(directory):
        return []
    files = [
        os.path.join(directory, f)
        for f in sorted(os.listdir(directory))
        if f.lower().endswith(AUDIO_EXT) and not f.startswith(".")
    ]
    return files


class StreamPlayer:
    """Low-latency player: one persistent output stream + software mixer.

    All sounds are decoded to float32 stereo once at construction. Playing a
    sound just appends a "voice" (a buffer plus a cursor) to a shared list;
    the audio callback sums the active voices into each output block. Because
    the stream and the audio device stay open for the whole session, a
    keystroke turns into sound on the next callback (single-digit ms) with no
    process spawn and no per-keystroke device initialisation.

    The concurrency limit (max_concurrent) drops the oldest voice when the
    cap is reached, keeping the mixing cost bounded under very fast typing.
    """

    def __init__(self, sounds, volume=1.0, max_concurrent=32, blocksize=0):
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        self.np = np
        self.volume = volume
        self.max_concurrent = max_concurrent
        self.channels = 2

        # Match the output device's native rate to avoid a resample in the
        # hot path; sounds are resampled once, at load time, only if needed.
        dev = sd.query_devices(kind="output")
        self.samplerate = int(dev["default_samplerate"])

        # Decode every sound into memory as contiguous float32 stereo.
        self.buffers = {}
        for path in sounds:
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            if data.shape[1] == 1:
                data = np.repeat(data, 2, axis=1)  # mono -> stereo
            elif data.shape[1] > 2:
                data = data[:, :2]
            if sr != self.samplerate:
                data = self._resample(data, sr, self.samplerate)
            self.buffers[path] = np.ascontiguousarray(data, dtype=np.float32)

        self._voices = []  # list of [buffer, position]
        self._lock = threading.Lock()
        self._stream = sd.OutputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="float32",
            blocksize=blocksize,  # 0 -> let PortAudio pick a low-latency size
            latency="low",
            callback=self._callback,
        )
        self._stream.start()

    def _resample(self, data, sr, target):
        """Linear resample; only used when a file's rate != device rate."""
        np = self.np
        n = data.shape[0]
        new_n = int(round(n * target / sr))
        if new_n <= 1 or n <= 1:
            return data
        x_old = np.linspace(0.0, 1.0, n, endpoint=False)
        x_new = np.linspace(0.0, 1.0, new_n, endpoint=False)
        out = np.empty((new_n, data.shape[1]), dtype=np.float32)
        for c in range(data.shape[1]):
            out[:, c] = np.interp(x_new, x_old, data[:, c])
        return out

    def _callback(self, outdata, frames, time_info, status):
        np = self.np
        outdata.fill(0.0)
        with self._lock:
            still = []
            for voice in self._voices:
                buf, pos = voice
                chunk = buf[pos:pos + frames]
                n = chunk.shape[0]
                if n:
                    outdata[:n] += chunk
                nxt = pos + frames
                if nxt < buf.shape[0]:
                    voice[1] = nxt
                    still.append(voice)
            self._voices = still
        if self.volume != 1.0:
            outdata *= self.volume
        # Summed/amplified voices can exceed [-1, 1]; clip to avoid overflow.
        np.clip(outdata, -1.0, 1.0, out=outdata)

    def play_many(self, paths):
        """Play several sounds at once (for chaos)."""
        with self._lock:
            for path in paths:
                buf = self.buffers.get(path)
                if buf is None:
                    continue
                # If over the concurrency cap, drop the oldest voice.
                while len(self._voices) >= self.max_concurrent:
                    self._voices.pop(0)
                self._voices.append([buf, 0])

    def stop_all(self):
        with self._lock:
            self._voices = []

    def close(self):
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass


class SoundPlayer:
    """Fallback player: launch afplay non-blocking, cap concurrent plays.

    One `afplay` process is spawned per keystroke. The concurrency limit
    (max_concurrent) plus process reaping keep the number of afplay processes
    bounded even under very fast typing. This path is simpler than
    StreamPlayer but adds latency, since each keystroke re-initialises the
    audio pipeline from scratch.
    """

    def __init__(self, volume=1.0, max_concurrent=32):
        self.volume = volume
        self.max_concurrent = max_concurrent
        self._procs = []
        self._lock = threading.Lock()

    def _reap(self):
        # Drop finished processes from the list.
        self._procs = [p for p in self._procs if p.poll() is None]

    def play_many(self, paths):
        """Play several sounds at once (for chaos)."""
        with self._lock:
            self._reap()
            for path in paths:
                # If over the concurrency cap, stop the oldest play.
                while len(self._procs) >= self.max_concurrent:
                    oldest = self._procs.pop(0)
                    oldest.terminate()
                cmd = ["afplay"]
                if abs(self.volume - 1.0) > 1e-9:
                    cmd += ["-v", str(self.volume)]
                cmd.append(path)
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except FileNotFoundError:
                    print("Error: afplay not found (macOS only).", file=sys.stderr)
                    return
                self._procs.append(proc)

    def stop_all(self):
        with self._lock:
            for p in self._procs:
                p.terminate()
            self._procs.clear()

    def close(self):
        self.stop_all()


def create_player(sounds, volume, max_concurrent, force_afplay=False):
    """Build the best available player.

    Returns (player, backend_name). Prefers the low-latency StreamPlayer and
    falls back to the afplay SoundPlayer if the audio libraries are missing or
    the output stream cannot be opened.
    """
    if not force_afplay:
        try:
            player = StreamPlayer(
                sounds, volume=volume, max_concurrent=max_concurrent
            )
            return player, "stream"
        except Exception as e:
            print(
                f"Low-latency backend unavailable ({e}); using afplay.\n"
                f"  For the low-latency backend: "
                f"./.venv/bin/python -m pip install sounddevice numpy soundfile",
                file=sys.stderr,
            )
    return SoundPlayer(volume=volume, max_concurrent=max_concurrent), "afplay"


class ChaosKeyboard:
    """Handler that turns key presses into animal sounds.

    Besides being passed to the pynput listener, its on_press/on_release can
    be called directly from tests to verify "one keystroke -> sound" and
    auto-repeat suppression.
    """

    def __init__(self, player, sounds, sounds_per_key=3, allow_repeat=False,
                 rng=None):
        self.player = player
        self.sounds = sounds
        self.sounds_per_key = max(1, sounds_per_key)
        self.allow_repeat = allow_repeat
        self.rng = rng or random
        self.pressed = set()
        self.press_count = 0  # keystrokes actually played (for tests/debug)

    @staticmethod
    def key_id(key):
        # Identifier used to detect auto-repeat.
        try:
            return key.char
        except AttributeError:
            return key

    def on_press(self, key):
        kid = self.key_id(key)
        if not self.allow_repeat:
            if kid in self.pressed:
                return  # ignore auto-repeat (key held down)
            self.pressed.add(kid)
        # Pick 1..sounds_per_key sounds at random and layer them (chaos).
        k = self.rng.randint(1, self.sounds_per_key)
        chosen = [self.rng.choice(self.sounds) for _ in range(k)]
        self.player.play_many(chosen)
        self.press_count += 1
        if os.environ.get("CHAOS_DEBUG"):
            animals = ", ".join(
                os.path.splitext(os.path.basename(c))[0] for c in chosen
            )
            print(f"[{self.press_count}] keypress -> {animals}", flush=True)

    def on_release(self, key):
        self.pressed.discard(self.key_id(key))


def main():
    parser = argparse.ArgumentParser(
        description="Play a random animal sound on every keystroke."
    )
    parser.add_argument(
        "-v", "--volume", type=float, default=1.0,
        help="Volume (values above 1.0 amplify. Default 1.0).",
    )
    parser.add_argument(
        "-m", "--max-concurrent", type=int, default=32,
        help="Max concurrent plays; runaway safeguard (default 32).",
    )
    parser.add_argument(
        "-n", "--sounds-per-key", type=int, default=3,
        help="Max sounds layered per keystroke; chaos level (default 3).",
    )
    parser.add_argument(
        "--allow-repeat", action="store_true",
        help="Also fire on key auto-repeat (held key). Even more chaos.",
    )
    parser.add_argument(
        "--legacy-afplay", action="store_true",
        help="Force the afplay backend (one process per keystroke; higher "
             "latency). Default is the low-latency in-process mixer.",
    )
    args = parser.parse_args()
    if args.sounds_per_key < 1:
        args.sounds_per_key = 1

    sounds = load_sounds(SOUNDS_DIR)
    if not sounds:
        print(f"Error: no sounds found in {SOUNDS_DIR}", file=sys.stderr)
        print("Run fetch_sounds.py first to download sounds.", file=sys.stderr)
        return 1

    try:
        from pynput import keyboard
    except ImportError:
        print("Error: pynput is not installed.", file=sys.stderr)
        print("  ./.venv/bin/python -m pip install pynput", file=sys.stderr)
        return 1

    player, backend = create_player(
        sounds, args.volume, args.max_concurrent,
        force_afplay=args.legacy_afplay,
    )
    chaos = ChaosKeyboard(
        player, sounds,
        sounds_per_key=args.sounds_per_key,
        allow_repeat=args.allow_repeat,
    )

    names = ", ".join(os.path.splitext(os.path.basename(s))[0] for s in sounds)
    print(f"Animal sounds: {len(sounds)} kinds ({names})")
    backend_desc = (
        "in-process mixer (low latency)" if backend == "stream"
        else "afplay (one process per keystroke)"
    )
    print(f"Backend: {backend_desc}")
    print(f"Chaos: up to {args.sounds_per_key} sounds per keystroke / "
          f"volume {args.volume} / concurrency cap {args.max_concurrent}")
    print("Type on the keyboard to make noise. Quit with Ctrl+C.")
    print("(First run needs macOS 'Input Monitoring' permission.)")

    listener = keyboard.Listener(
        on_press=chaos.on_press, on_release=chaos.on_release
    )
    listener.start()
    try:
        listener.join()
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        player.close()
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
