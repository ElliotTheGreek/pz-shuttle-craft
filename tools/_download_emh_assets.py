from pathlib import Path
from urllib.request import urlretrieve

ASSETS = {
    Path("tools/assets/trek_emh/trek_emh.glb"): "https://v3.fal.media/files/elephant/-LwXafIkkdyc8DiSVigOw.glb",
    Path("design/art/emh/emh_concept_raw.png"): "https://v3.fal.media/files/panda/2AoqLQQeNxZLG1riXEctm.png",
}

for path, url in ASSETS.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(url, path)
    if path.stat().st_size == 0:
        raise RuntimeError(f"empty download: {path}")
    print(f"{path}: {path.stat().st_size} bytes")
