#!/bin/bash
cd "$(dirname "$0")" || exit 1
python3 local_launcher.py
result=$?
if [ "$result" -ne 0 ]; then
  echo "Install Python 3.12 or newer, with Tk, from https://www.python.org/downloads/macos/"
  echo "Press Return to close."
  read -r
fi
exit "$result"
