"""The hydroponics item icons (FARMING.md): keyed from Gemini raws.

    python tools/gen_farm_icons.py

Every raw is generated on flat magenta and kept in design/art/food/farm/ (a
regenerated picture is a different picture). Each is keyed to a 64x64
media/textures/Item_TREK_<name>.png by tools/key_icon.py.

**The seven seed packets are one picture.** The packet was drawn with a plain
white label band; each crop's packet is that raw with the label tinted the
crop's colour, so the packets read as a set and cost one generation.
"""
import os
import sys
import urllib.request

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import key_icon  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "design", "art", "food", "farm")
TEX = os.path.join(ROOT, "TrekShuttle", "42", "media", "textures")
U = "https://flowdot-user-images.s3.us-east-1.amazonaws.com/23/"

RAWS = {
    "SeedPacket": "1f59a0b7-6b08-4f5c-91f5-fc3174bc21c0.jpg",
    "TeaLeaves": "f1eeb4c0-6fd8-4509-aa11-8fadeb8846bd.jpg",
    "Bergamot": "ce6c2a5b-b67d-4aba-9674-cb5b842258cf.jpg",
    "CoffeeCherries": "fffaff70-5f56-4af4-8707-8b980e12ba23.jpg",
    "Plomeek": "8d686217-801b-48a2-850d-5758164af9a3.jpg",
    "LeolaRoot": "64848438-ab11-4a82-ab7e-f43649f4795d.jpg",
    "AndorianTuberRaw": "a654c3ff-8047-4c0d-aa39-dfd7f23faf76.jpg",
    "HasperatPeppers": "b2370f16-2053-4748-a39e-d0ddf466d75f.jpg",
    "TeaDried": "0ff749f5-897d-4fd7-8c97-4aa151fbd23d.jpg",
    "BergamotZest": "b0c43c03-66bf-4be0-8994-f0632c05b67e.jpg",
    "CoffeeBeans": "12578595-f9ef-448a-8ecb-02cb4983e49f.jpg",
    "CoffeeGround": "e679b069-92e3-4bdd-81be-36d0609cfd59.jpg",
    "HasperatDried": "63638760-64ee-4a04-ba28-13d8c180605b.jpg",
    "SerpentWorm": "7ee8ba50-5926-44df-b550-7241d9718ebe.jpg",
}

# Each seed packet's label colour: the crop's own.
SEEDS = {
    "SeedTea": (70, 150, 70),
    "SeedBergamot": (200, 200, 60),
    "SeedKlingonCoffee": (150, 40, 40),
    "SeedPlomeek": (220, 110, 50),
    "SeedLeola": (130, 80, 140),
    "SeedAndorianTuber": (110, 170, 220),
    "SeedHasperat": (230, 60, 30),
}


def raw_path(name):
    return os.path.join(RAW, name + "_raw.jpg")


def fetch():
    os.makedirs(RAW, exist_ok=True)
    for name, url in RAWS.items():
        p = raw_path(name)
        if not os.path.exists(p):
            urllib.request.urlretrieve(U + url, p)


def magenta_panel(path):
    """The raw cropped to its magenta canvas.

    Asked for an icon on a magenta background, the model sometimes draws the
    magenta canvas as a panel *inside* a bigger picture -- a white or grey
    surround, once a whole screenshot of a paint program round it -- and the
    key then reads the surround as the background and keeps the panel as a
    solid square. So the magenta itself is found and everything outside it
    cut away before keying."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if r > 190 and b > 190 and g < 90:
                xs.append(x)
                ys.append(y)
    if not xs:
        return img
    box = (min(xs) + 3, min(ys) + 3, max(xs) - 3, max(ys) - 3)
    return img.crop(box)


def prepared(name):
    """A raw ready to key: cropped to its magenta, saved beside the raw."""
    out = os.path.join(RAW, name + "_panel.png")
    magenta_panel(raw_path(name)).save(out)
    return out


def tint_label(img, colour):
    """Recolours the packet's white label: bright, unsaturated pixels take the
    crop's colour, keeping their shading."""
    img = img.convert("RGB")
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = px[x, y]
            hi, lo = max(r, g, b), min(r, g, b)
            magenta = r > 150 and b > 150 and g < 110
            if hi > 205 and hi - lo < 28 and not magenta:
                k = hi / 255.0
                px[x, y] = tuple(int(c * k) for c in colour)
    return img


def main():
    fetch()
    made = []
    for name in RAWS:
        if name == "SeedPacket":
            continue
        out = os.path.join(TEX, "Item_TREK_%s.png" % name)
        key_icon.key(prepared(name), out)
        made.append(name)
    packet = Image.open(prepared("SeedPacket"))
    for name, colour in SEEDS.items():
        tmp = os.path.join(RAW, name + "_tinted.png")
        tint_label(packet, colour).save(tmp)
        key_icon.key(tmp, os.path.join(TEX, "Item_TREK_%s.png" % name))
        made.append(name)
    print("keyed %d icons" % len(made))


if __name__ == "__main__":
    main()
