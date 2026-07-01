#!/bin/bash
# Play an animal sound for each keyboard keystroke (chaos mode).
# Quit with Ctrl+C. Arguments are passed straight through to animal_keys.py.
#   e.g. ./run.sh -n 5 -v 1.5   (up to 5 sounds per keystroke, 1.5x volume)
cd "$(dirname "$0")" || exit 1
exec ./.venv/bin/python animal_keys.py "$@"
