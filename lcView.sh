#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
rm -rf "$DIR/scripts/.temp_lcView"
mkdir "$DIR/scripts/.temp_lcView/"
python3 "$DIR/scripts/lcdft.py"
rm -r "$DIR/scripts/.temp_lcView"