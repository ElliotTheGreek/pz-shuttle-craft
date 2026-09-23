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
lines = text.splitlines()
lines = [
    "name=Shuttlecraft [DEV]" if line == "name=Shuttlecraft" else
    "id=TrekShuttleDev" if line == "id=TrekShuttle" else
    line + "-dev" if line.startswith("modversion=") and not line.endswith("-dev") else
    line
    for line in lines
]
text = "\n".join(lines) + "\n"
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

dev_version = next((line.split("=", 1)[1] for line in lines
                    if line.startswith("modversion=")), "")
if ("id=TrekShuttleDev" not in lines
        or "name=Shuttlecraft [DEV]" not in lines
        or not dev_version.endswith("-dev")):
    raise SystemExit("development mod identity was not written")
print("42\\mod.info", "TrekShuttleDev " + dev_version)

critical = [
    Path("42/media/models_X/TREK_Shuttle.x"),
    Path("42/media/textures/TREK_Shuttle.png"),
    Path("42/media/scripts/trekshuttle.txt"),
    Path("42/media/sound/TREK_PhaserPulse.wav"),
    Path("42/media/sandbox-options.txt"),
    Path("42/media/lua/shared/TREK/TREK_Config.lua"),
    Path("42/media/lua/shared/TREK/TREK_Util.lua"),
    Path("42/media/lua/shared/TREK/TREK_Net.lua"),
    Path("42/media/lua/shared/TREK/TREK_Ship.lua"),
    Path("42/media/lua/shared/TREK/TREK_World.lua"),
    Path("42/media/lua/shared/TREK/TREK_InteriorLayout.lua"),
    Path("42/media/lua/server/TREK/TREK_Build.lua"),
    Path("42/media/lua/server/TREK/TREK_Server.lua"),
    Path("42/media/lua/client/TREK/TREK_Core.lua"),
    Path("42/media/lua/client/TREK/TREK_Helm.lua"),
    Path("42/media/lua/client/TREK/TREK_Menu.lua"),
    Path("42/media/lua/client/TREK/TREK_VehicleMenu.lua"),
    Path("42/media/lua/shared/TREK/TREK_Vehicle.lua"),
    Path("42/media/scripts/vehicles/trekshuttle_vehicle.txt"),
    Path("42/media/models_X/TREK_Empty.x"),
    Path("42/media/ui/vehicles/seatui/trekshuttle_base_small.png"),
    Path("42/media/ui/TREK_LcarsDot.png"),
    Path("42/media/ui/TREK_HelmBackdrop.png"),
    Path("42/media/ui/TREK_HelmEmblem.png"),
    Path("42/media/lua/shared/Translate/EN/IG_UI.json"),
    Path("42/media/lua/shared/Translate/EN/Sandbox.json"),
    # The Doctor. His mesh and texture are the largest generated assets in the
    # mod after the hull, and a model that does not arrive draws nothing and
    # says nothing -- which is the failure this whole list exists to catch.
    Path("42/media/lua/shared/TREK/TREK_EMH.lua"),
    Path("42/media/lua/client/TREK/TREK_EMHUI.lua"),
    Path("42/media/models_X/TREK_EMH.x"),
    Path("42/media/textures/TREK_EMH.png"),
    Path("42/media/ui/TREK_EmhPortrait.png"),
    Path("42/media/sound/TREK_EmhAppear.wav"),
    # The wardrobe. The GUID table is the one file here whose absence is
    # completely silent: without it every uniform still equips, still weighs
    # something and draws nothing at all, because getClothingItem returns null
    # for an id the merged table does not know. A deploy that dropped it would
    # look exactly like a deploy that worked.
    Path("42/media/fileGuidTable.xml"),
    Path("42/media/clothing/clothingItems/TrekUniformDutyCommand.xml"),
    Path("42/media/clothing/clothingItems/TrekUniformDressCommand.xml"),
    Path("42/media/textures/clothes/trek/duty_command.png"),
    Path("42/media/textures/clothes/trek/dress_command.png"),
    Path("42/media/textures/Item_TREK_DutyCommand.png"),
]
for relative in critical:
    source_hash = digest(SOURCE / relative)
    deployed_hash = digest(DESTINATION / relative)
    if source_hash != deployed_hash:
        raise SystemExit("hash mismatch: " + str(relative))
    print(relative, source_hash[:16])

# Files from before the multiplayer split must not survive in the deployed
# copy: an old client-side TREK_Build.lua would build a second cabin locally.
#
# TREK_Flight.lua is deliberately not on this list any more. It was, because
# the 1.1 hands-on flight had been deleted and a leftover copy would have flown
# the pilot's body around; the name is now a new file that flies the shuttle as
# a vehicle on the sky plane, so its presence is correct rather than stale.
for stale in ("42/media/lua/client/TREK/TREK_Build.lua",
              "42/media/lua/client/TREK/TREK_SelfTest.lua",
              "42/media/lua/client/TREK/TREK_InteriorLayout.lua"):
    if (DESTINATION / stale).exists():
        raise SystemExit("stale pre-multiplayer file deployed: " + stale)

print("deployed", len(deployed_files), "files ->", DESTINATION)
print("critical deployed files verified; no pre-multiplayer files left")
