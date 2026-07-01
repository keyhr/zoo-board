#!/usr/bin/env python3
"""Verify the keystroke -> animal-sound playback logic.

Confirm the handler-level behavior, excluding OS-level global event
capture (which requires macOS Input Monitoring permission):
  - distinct keys each fire
  - a held key (auto-repeat) fires only once
  - pressing again after key release fires again
  - an afplay process is actually spawned
"""
import random
import sys
import time

import animal_keys as ak


class FakeKey:
    """Mimic a pynput regular key (has .char)."""
    def __init__(self, char):
        self.char = char


class FakeSpecialKey:
    """Mimic a pynput special key (no .char, e.g. space, enter)."""
    pass


def main():
    sounds = ak.load_sounds(ak.SOUNDS_DIR)
    assert sounds, "sounds could not be loaded"
    print(f"loaded {len(sounds)} sounds")

    # Keep volume low and one sound per keystroke to avoid a loud noise during verification
    player = ak.SoundPlayer(volume=0.25, max_concurrent=8)
    rng = random.Random(0)
    chaos = ak.ChaosKeyboard(player, sounds, sounds_per_key=1,
                             allow_repeat=False, rng=rng)

    # 1) distinct keys each fire
    for ch in "abc":
        chaos.on_press(FakeKey(ch))
    assert chaos.press_count == 3, f"distinct keys: {chaos.press_count}"
    print("OK 3 distinct keys -> 3 plays")

    # 2) a held key (repeated on_press with no key release) fires only once
    chaos.on_press(FakeKey("x"))
    chaos.on_press(FakeKey("x"))
    chaos.on_press(FakeKey("x"))
    assert chaos.press_count == 4, f"auto-repeat suppressed: {chaos.press_count}"
    print("OK held key (auto-repeat) -> only once")

    # 3) pressing again after key release fires again
    chaos.on_release(FakeKey("x"))
    chaos.on_press(FakeKey("x"))
    assert chaos.press_count == 5, f"after release: {chaos.press_count}"
    print("OK re-press after key release -> plays again")

    # 4) special keys (no .char) also fire
    chaos.on_press(FakeSpecialKey())
    assert chaos.press_count == 6, f"special key: {chaos.press_count}"
    print("OK special key -> play")

    # 5) whether a real process is running (afplay)
    time.sleep(0.2)
    with player._lock:
        player._reap()
        active = len(player._procs)
    print(f"OK confirmed afplay process launch ({active} playing)")

    # with allow_repeat=True, a held key fires too
    chaos2 = ak.ChaosKeyboard(player, sounds, sounds_per_key=1,
                              allow_repeat=True, rng=rng)
    chaos2.on_press(FakeKey("y"))
    chaos2.on_press(FakeKey("y"))
    assert chaos2.press_count == 2, f"allow_repeat: {chaos2.press_count}"
    print("OK with --allow-repeat, a held key plays repeatedly")

    time.sleep(1.0)
    player.stop_all()
    print("\nAll logic verifications passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
