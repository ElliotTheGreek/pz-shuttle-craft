import os
import urllib.request

BASE = "https://raw.githubusercontent.com/Malcolmnixon/Quaternius-Ultimate-Spaceships-Pack/main/"
FILES = {
    "screenshot.png": "img/screenshot.png",
    "challenger_base.tscn": "addons/quaternius-ultimate-spaceships-pack/meshes/challenger/mesh/challenger_base.tscn",
    "dispatcher_base.tscn": "addons/quaternius-ultimate-spaceships-pack/meshes/dispatcher/mesh/dispatcher_base.tscn",
    "LICENSE": "LICENSE",
    "Dispatcher.blend": "blender/Dispatcher.blend",
    "Dispatcher_Blue.png": "addons/quaternius-ultimate-spaceships-pack/meshes/dispatcher/textures/Dispatcher_Blue.png",
}
os.makedirs(".asset-import/candidates", exist_ok=True)
for output_name, source_path in FILES.items():
    url = BASE + source_path
    with urllib.request.urlopen(url) as response:
        content = response.read()
    output_path = os.path.join(".asset-import", "candidates", output_name)
    with open(output_path, "wb") as output:
        output.write(content)
    print(output_name, len(content), "bytes")

import json
api_url = "https://api.github.com/repos/Malcolmnixon/Quaternius-Ultimate-Spaceships-Pack/git/trees/main?recursive=1"
request = urllib.request.Request(api_url, headers={"User-Agent": "pz-trekship-asset-import"})
with urllib.request.urlopen(request) as response:
    tree = json.load(response)["tree"]
for item in tree:
    path = item["path"]
    if "dispatcher" in path.lower() or path.startswith("blender/"):
        print(item["type"], item.get("size", "-"), path)
