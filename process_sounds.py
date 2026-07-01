#!/usr/bin/env python3
"""Process the original sound files in raw/ into short clips suited for keystrokes and output them to sounds/.

For each sound file, ffmpeg applies the following:
  1. Leading-silence removal (prevents silence at the start of a recording from producing a "silent keystroke")
  2. Shorten to about 2 seconds (long clips pile up during rapid keystrokes)
  3. Loudness normalization + limiter (make all animals uniformly loud -- for chaos)
  4. Slight fade in/out (removes clicks at the cut edges)

If raw/ has no gorilla, synthesize a low-frequency chest-beat-like sound to fill in
(because no real gorilla animal-sound file exists on Wikimedia Commons).
"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE, "raw")
OUT_DIR = os.path.join(BASE, "sounds")

TARGET_SEC = 2.0
FADE_OUT_AT = TARGET_SEC - 0.25
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".oga", ".flac", ".m4a", ".aiff", ".aif", ".opus")

# Filter chain that turns sounds into keystrokes
# The trailing loudnorm is EBU R128 perceptual loudness normalization. It uses a
# relatively high target of I=-11 to align all animals to a uniform, loud level (for chaos).
# The TP=-1 true-peak limit prevents clipping.
FILTER = (
    "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB,"
    f"atrim=0:{TARGET_SEC},asetpts=N/SR/TB,"
    "afade=t=in:st=0:d=0.02,"
    f"afade=t=out:st={FADE_OUT_AT}:d=0.25,"
    "loudnorm=I=-11:TP=-1.0:LRA=11"
)


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, text=True)


def synth_gorilla(dest_wav):
    """Synthesize a low-frequency chest-beat/growl-like sound."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=85:duration=2.2",
        "-f", "lavfi", "-i", "anoisesrc=duration=2.2:color=brown:amplitude=0.5",
        "-filter_complex",
        "[0]tremolo=f=8:d=1[s];"      # pulse at 8Hz to create thump-thump
        "[1]lowpass=f=350[n];"         # restrict brown noise to low frequencies
        "[s][n]amix=inputs=2:weights=1 0.7,lowpass=f=520,highpass=f=40",
        dest_wav,
    ]
    r = run(cmd)
    if r.returncode != 0:
        print("WARN: gorilla synthesis failed:\n" + (r.stderr or "")[-400:], file=sys.stderr)
        return False
    return True


def process(src, dest):
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-af", FILTER,
        "-ac", "2", "-ar", "44100",
        "-codec:a", "libmp3lame", "-q:a", "4",
        dest,
    ]
    r = run(cmd)
    if r.returncode != 0:
        print(f"FAIL {os.path.basename(src)}:\n" + (r.stderr or "")[-400:],
              file=sys.stderr)
        return False
    return True


def main():
    if subprocess.run(["which", "ffmpeg"], stdout=subprocess.DEVNULL).returncode != 0:
        print("Error: ffmpeg is required.", file=sys.stderr)
        return 1

    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    # If there is no original for gorilla, synthesize one to fill in
    has_gorilla = any(
        f.lower().startswith("gorilla.") for f in os.listdir(RAW_DIR)
    )
    if not has_gorilla:
        print("synth gorilla (chest-beat) ...")
        synth_gorilla(os.path.join(RAW_DIR, "gorilla.wav"))

    raw_files = sorted(
        f for f in os.listdir(RAW_DIR)
        if f.lower().endswith(AUDIO_EXT) and not f.startswith(".")
    )
    if not raw_files:
        print(f"Error: no originals found: {RAW_DIR}", file=sys.stderr)
        return 1

    ok = 0
    for f in raw_files:
        name = os.path.splitext(f)[0]
        src = os.path.join(RAW_DIR, f)
        dest = os.path.join(OUT_DIR, f"{name}.mp3")
        if process(src, dest):
            dur = subprocess.run(
                ["afinfo", dest], capture_output=True, text=True
            ).stdout
            sec = ""
            for line in dur.splitlines():
                if "estimated duration" in line:
                    sec = line.split(":")[-1].strip()
            print(f"OK   {name:10s} -> sounds/{name}.mp3  ({sec})")
            ok += 1

    print(f"\nProcessed {ok}/{len(raw_files)} sounds into {OUT_DIR}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
