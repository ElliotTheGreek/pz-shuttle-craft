"""Deploy TrekShuttle to the current Windows user's Project Zomboid mods folder."""
import hashlib
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "TrekShuttle"
DESTINATION = Path.home() / "Zomboid" / "mods" / "TrekShuttle"

if DESTINATION.exists():
    shutil.rmtree(DESTINATION)
DESTINATION.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(SOURCE, DESTINATION)

source_files = sorted(path.relative_to(SOURCE) for path in SOURCE.rglob("*") if path.is_file())
deployed_files = sorted(path.relative_to(DESTINATION) for path in DESTINATION.rglob("*") if path.is_file())
if source_files != deployed_files:
    raise SystemExit("deployed file list does not match source")

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

critical = [
    Path("42/mod.info"),
    Path("42/media/models_X/TREK_Shuttle.x"),
    Path("42/media/textures/TREK_Shuttle.png"),
    Path("42/media/scripts/trekshuttle.txt"),
]
for relative in critical:
    source_hash = digest(SOURCE / relative)
    deployed_hash = digest(DESTINATION / relative)
    if source_hash != deployed_hash:
        raise SystemExit("hash mismatch: " + str(relative))
    print(relative, source_hash[:16])

print("deployed", len(deployed_files), "files ->", DESTINATION)
print("critical deployed files match the validated build")
