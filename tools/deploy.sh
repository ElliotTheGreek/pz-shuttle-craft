#!/bin/sh
# Copies the mod into the Project Zomboid mods folder for testing.
SRC="$(cd "$(dirname "$0")/.." && pwd)/TrekShuttle"
DEST="/c/Users/Arcade/Zomboid/mods/TrekShuttle"
rm -rf "$DEST"
mkdir -p "$DEST"
cp -r "$SRC/." "$DEST/"
echo "deployed -> $DEST"
find "$DEST" -type f | wc -l
