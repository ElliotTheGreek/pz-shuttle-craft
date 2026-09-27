"""The contraband item icons: keyed from Gemini raws.

    python tools/gen_contraband_icons.py

Every raw is generated on flat magenta and kept in design/art/contraband/ (a
regenerated picture is a different picture). Each is keyed to a 64x64
media/textures/Item_TREK_<name>.png by tools/key_icon.py, after being cropped
to its magenta panel (gen_farm_icons.magenta_panel).

The three drug vials are told apart by shape and colour at 32px: a grey
cartridge of white fluid, a round amber-granule bottle, a squat green hazard
canister, and a long thin yellow hypo ampoule.
"""
import os
import sys
import urllib.request

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import key_icon  # noqa: E402
from gen_farm_icons import magenta_panel  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "design", "art", "contraband")
TEX = os.path.join(ROOT, "TrekShuttle", "42", "media", "textures")
U = "https://flowdot-user-images.s3.us-east-1.amazonaws.com/23/"

RAWS = {
    "KetracelWhite": "8a96c4dd-bb13-41a5-b576-546c4d1b0a15.jpg",
    "KtarianGame": "10f2f21b-5169-44d8-aebb-bdf548686f15.jpg",
    "Felicium": "fc6c68bf-ccf0-4fe1-adea-3e2defd2f40c.jpg",
    "TrelliumD": "16ecf29d-5d0d-4945-958a-d8312cf7e61c.jpg",
    "Cordrazine": "b3a5cae3-a89e-4a83-8aef-25b2a55a0816.jpg",
    "Kanar": "ad10a1da-667b-4669-a2cf-48080c9db795.jpg",  # deleted from the bucket; the raw here is the copy
    "SaurianBrandy": "6c06e73b-b4b8-413a-a732-46bb20e7f2dc.jpg",
    "AldebaranWhiskey": "c11b8012-4a06-4804-bfe0-a12d7305ab76.jpg",
    "LatinumStrip": "617a3dd2-64d4-45cc-bed5-cb32beb7f82f.jpg",
}

# The kanar raw came back as two bottles side by side; the left one is whole,
# so the raw is cut to it before the magenta crop.
CROPS = {
    "Kanar": (0, 0, 680, 768),
}


def raw_path(name):
    return os.path.join(RAW, name + "_raw.jpg")


def fetch():
    os.makedirs(RAW, exist_ok=True)
    for name, url in RAWS.items():
        p = raw_path(name)
        if not os.path.exists(p):
            urllib.request.urlretrieve(url if "://" in url else U + url, p)


def prepared(name):
    """A raw ready to key: cropped to its magenta, saved beside the raw."""
    out = os.path.join(RAW, name + "_panel.png")
    src = raw_path(name)
    if name in CROPS:
        src = os.path.join(RAW, name + "_cut.png")
        Image.open(raw_path(name)).crop(CROPS[name]).save(src)
    magenta_panel(src).save(out)
    return out


def main():
    fetch()
    for name in RAWS:
        print(name)
        key_icon.key(prepared(name),
                     os.path.join(TEX, "Item_TREK_%s.png" % name))
    print("keyed %d icons" % len(RAWS))


if __name__ == "__main__":
    main()
