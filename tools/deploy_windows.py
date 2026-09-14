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

# A subscribed Workshop build may also provide id=TrekShuttle. Project
# Zomboid cannot reliably distinguish two providers of the same internal ID,
# so local testing gets a development-only identity. The canonical source and
# Workshop package keep the release ID; only the deployed copy is rewritten.
info = DESTINATION / "42" / "mod.info"
text = info.read_text(encoding="utf-8")
text = text.replace("name=Shuttlecraft\n", "name=Shuttlecraft [DEV FLIGHT]\n", 1)
text = text.replace("id=TrekShuttle\n", "id=TrekShuttleDev\n", 1)
text = text.replace("modversion=1.0.0\n", "modversion=1.4.0-dev\n", 1)
info.write_text(text, encoding="utf-8")

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

if ("id=TrekShuttleDev" not in text
        or "name=Shuttlecraft [DEV FLIGHT]" not in text
        or "modversion=1.4.0-dev" not in text):
    raise SystemExit("development mod identity was not written")
print("42\\mod.info", "TrekShuttleDev 1.4.0-dev")

critical = [
    Path("42/media/models_X/TREK_Shuttle.x"),
    Path("42/media/textures/TREK_Shuttle.png"),
    Path("42/media/scripts/trekshuttle.txt"),
    Path("42/media/lua/client/TREK/TREK_Flight.lua"),
    Path("42/media/lua/client/TREK/TREK_Menu.lua"),
    Path("42/media/lua/shared/Translate/EN/IG_UI.json"),
]
for relative in critical:
    source_hash = digest(SOURCE / relative)
    deployed_hash = digest(DESTINATION / relative)
    if source_hash != deployed_hash:
        raise SystemExit("hash mismatch: " + str(relative))
    print(relative, source_hash[:16])

flight = (DESTINATION / "42/media/lua/client/TREK/TREK_Flight.lua").read_text(encoding="utf-8")
menu = (DESTINATION / "42/media/lua/client/TREK/TREK_Menu.lua").read_text(encoding="utf-8")
labels = (DESTINATION / "42/media/lua/shared/Translate/EN/IG_UI.json").read_text(encoding="utf-8")
if "FLIGHT BUILD 1.4" not in flight:
    raise SystemExit("deployed flight controller marker is missing")
if 'require "TREK/TREK_Flight"' not in menu:
    raise SystemExit("deployed menu does not load the flight controller")
if "Pilot the shuttle [FLIGHT 1.4]" not in labels:
    raise SystemExit("deployed visible flight label is missing")

print("deployed", len(deployed_files), "files ->", DESTINATION)
print("critical deployed files and FLIGHT BUILD 1.4 markers verified")
