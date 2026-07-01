#!/usr/bin/env python3
"""Play a random animal sound on every keystroke.

- Watches global key-press events via pynput.
- On each press, picks random sound(s) from sounds/ and plays them with afplay.
- Ignores key auto-repeat so that one physical keystroke maps to one trigger.

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


class SoundPlayer:
    """Launch afplay non-blocking and cap the number of concurrent plays.

    The concurrency limit (max_concurrent) plus process reaping keep the
    number of afplay processes bounded even under very fast typing.
    This is the safeguard that keeps the tool from harming the machine.
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
        help="Volume (afplay -v; values above 1.0 amplify. Default 1.0).",
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
        print("  ./.venv/bin/pip install pynput", file=sys.stderr)
        return 1

    player = SoundPlayer(volume=args.volume, max_concurrent=args.max_concurrent)
    chaos = ChaosKeyboard(
        player, sounds,
        sounds_per_key=args.sounds_per_key,
        allow_repeat=args.allow_repeat,
    )

    names = ", ".join(os.path.splitext(os.path.basename(s))[0] for s in sounds)
    print(f"Animal sounds: {len(sounds)} kinds ({names})")
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
        player.stop_all()
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
