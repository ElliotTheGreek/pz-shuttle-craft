#!/usr/bin/env python3
"""Decode BuildingEd furniture and identify placed container tiles."""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TBX = ROOT / "design/buildinged/TrekShuttle_Interior.tbx"
CATALOG = ROOT / "tools/_catalog/tiles.json"


def norm(name):
    match = re.match(r"^(.*_)(\d+)$", name)
    return match.group(1) + str(int(match.group(2))) if match else name


def container(props):
    for key, value in props.items():
        if key.lower() == "container" and value not in (None, "", "false", False):
            return str(value)
    return ""


def decode(tbx_path, catalog_path):
    root = ET.parse(tbx_path).getroot()
    raw = json.loads(catalog_path.read_text(encoding="utf-8")).get("tiles", {})
    catalog = {norm(name): props for name, props in raw.items()}
    definitions = []
    for furniture in root.findall("furniture"):
        orientations = {}
        for entry in furniture.findall("entry"):
            orientations[entry.get("orient", "")] = [
                (int(tile.get("x", "0")), int(tile.get("y", "0")), norm(tile.get("name", "")))
                for tile in entry.findall("tile")
            ]
        definitions.append((furniture.get("layer", "Furniture"), orientations))
    placed = []
    for floor_index, floor in enumerate(root.findall("floor")):
        for obj in floor.findall("object"):
            if obj.get("type") != "furniture":
                continue
            index = int(obj.get("FurnitureTiles"))
            orient = obj.get("orient", "")
            x, y = int(obj.get("x")), int(obj.get("y"))
            layer, orientations = definitions[index]
            tiles = orientations.get(orient, [])
            if not tiles and orient in ("E", "N"):
                tiles = orientations.get("W", [])
            elif not tiles and orient == "S":
                tiles = orientations.get("N", []) or orientations.get("W", [])
            if not tiles:
                raise ValueError(f"furniture {index} has no usable {orient!r} orientation")
            for px, py, sprite in tiles:
                props = catalog.get(sprite, {})
                placed.append({"floor": floor_index, "x": x + px, "y": y + py,
                               "sprite": sprite, "layer": layer, "container": container(props)})
    return root, placed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tbx", type=Path, default=TBX)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root, placed = decode(args.tbx, args.catalog)
    containers = [item for item in placed if item["container"]]
    if args.json:
        print(json.dumps({"width": int(root.get("width")), "height": int(root.get("height")),
                          "tiles": placed, "containers": containers}, indent=2))
    else:
        print(f"Expanded {len(placed)} furniture tiles; found {len(containers)} containers")
        for item in containers:
            print(f"{item['x']},{item['y']} {item['sprite']} container={item['container']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
