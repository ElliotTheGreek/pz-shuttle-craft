"""The cabin in another people's hands: every piece of it, and how each was asked for.

tools/adirondack_objects.py is Starfleet's list; this is the Klingons' and the Vulcans', for the
pieces a shuttle's cabin is built of and no more (TREK_Interiors.lua). Each is made the way
ADIRONDACK.md 7 makes Starfleet's: **a concept** from an image model, one shared style for a
people and a front view on a plain ground; **a mesh** from that concept (fal TRELLIS, seed 1701);
**tiles** from the mesh, every facing a turn of the one model (tools/gen_species_tiles.py).

kind
  model    a concept turned into a mesh and rendered into tiles
  flat     a picture laid on a wall face (a light, a display)
  surface  a flat material the generator cuts into walls and floors: never a tile by itself

A piece's name is Starfleet's name for the piece it stands in for, and that is the whole of how
it is found: it is rendered at the size tools/adirondack_objects.py gives that piece and put in
the same cell of its people's sheet, so it has that tile's properties and the cabin's plan needs
no other name for it. Two of Starfleet's are modelled in boxes there (the tape rack, the
television's cabinet); here they are models like the rest, at the same size.

tools/species_jobs.py is the ledger: every concept's and mesh's URL, and `fetch`. **The raws are
kept** (design/art/species/<people>/, tools/assets/species/<people>/): asked for again, an image
model gives a different object.
"""
import adirondack_objects as A

SHOT = ("Front view, seen straight on and slightly from above, the whole object in frame and centred, isolated on a "
        "plain flat light-grey background, soft even studio lighting, no cast shadow. ")
NOTHING = "No text, no numbers, no logos, no insignia, no people. "

STYLE = {
    "klingon": (
        "Product render of a single piece of furniture from the interior of a Klingon warship, in the heavy, martial "
        "style of Klingon ship interiors. " + SHOT +
        "Materials: dark forged gunmetal and oxidised bronze armour plating with heavy riveted seams, angular faceted "
        "shapes with pointed blade-like edges and ribbed buttresses, dark oxblood leather, small deep-red and amber "
        "lights. " + NOTHING),
    "vulcan": (
        "Product render of a single piece of furniture from the interior of a Vulcan starship, in the austere, serene, "
        "ceremonial style of Vulcan design. " + SHOT +
        "Materials: warm burnished bronze and copper metal, smooth sandstone-coloured ceramic panels, deep red-brown "
        "woven fabric, elegant curved and tapered geometric forms with fine engraved line patterns, small soft teal "
        "lights. " + NOTHING),
}

# What each people's piece is, after its style: (kind, what was asked).
PIECES = {
    "klingon": {
        "stasis_unit": ("model", "A tall food stasis unit (a warship's refrigerator): a heavy upright armoured cabinet with a peaked angular top, a single thick door with a forged vertical bar handle, and a small glowing red status panel."),
        "bunk": ("model", "A two-tier bunk bed built into a heavy armoured wall frame: two hard sleeping shelves with thin dark oxblood leather pads and a rolled fur blanket, a short forged ladder at one end, a small red light in each berth."),
        "arms_locker": ("model", "A tall narrow weapons rack locker standing against a wall: a heavy armoured frame with an open barred front, holding two long curved bladed weapons upright and a row of dark hand disruptor pistols on a shelf, a small red status light."),
        "galley_range": ("model", "A compact warship galley cooking range, waist height: a heavy dark iron cabinet with a flat black cooktop with four dull red glowing rings on top, an armoured oven door with a narrow dark glass slit below, forged knobs."),
        "galley_sink": ("model", "A galley counter unit, waist height: a deep hammered-metal basin sink set into its dark iron worktop and a heavy angular tap; armoured cabinet doors below."),
        "medical_cabinet": ("model", "A tall field medical supply cabinet standing against a wall: a dark armoured unit with a thick smoked-glass door showing crude surgical instruments, injectors and bandage rolls on its shelves, a small red status light."),
        "bridge_chair": ("model", "A warship officer's seat: a high-backed angular throne-like chair in dark oxblood leather with a ribbed metal frame and pointed shoulder tips, one armrest control panel, on a heavy pedestal."),
        "biobed": ("model", "A warship surgeon's medical bed, seen from its long side: a hard padded dark leather slab on a heavy armoured base, a small display panel of red lights at the head, and a low angular arched scanner frame over the chest area."),
        "tape_rack": ("model", "A tall open shelf rack that stands flat against a wall: a dark forged-metal frame with four shallow shelves holding rows of small rectangular data cartridges."),
        "tv_cabinet": ("model", "A low squat equipment cabinet, only knee height and as wide as it is deep: a dark armoured chest with two small riveted doors on its front and a flat top."),
        "wall_sconce": ("flat", "A slim wall light of a Klingon warship seen exactly front-on, flat, no perspective: a vertical angular forged-metal cage around a glowing deep red-amber panel, on a dark iron mount. Centred, isolated on a plain flat light-grey background, even lighting, no cast shadow. No text, no symbols."),
        "science_display": ("flat", "A wide wall-mounted Klingon warship tactical display screen seen exactly front-on, flat, no perspective: a black screen showing an abstract star chart in red and amber with angular interface frames and bar graphs, inside a thin dark metal bezel. The screen fills the whole image edge to edge. No text, no letters, no numbers, no symbols."),
        "wall": ("surface", "A flat, front-on texture of one section of a Klingon warship's interior bulkhead wall. Dark gunmetal armour plate with heavy riveted seams and a few slanted buttress ribs, a thin horizontal dull-red light strip about a third of the way down from the top, and a darker heavy kick plate along the bottom. A flat pattern: nothing mounted on it, nothing standing in front of it, no perspective, even flat lighting, the wall surface fills the whole image edge to edge. Slightly worn, uneven patina. No text, no symbols."),
        "deck": ("surface", "A flat top-down texture of a Klingon warship's deck plating: dark oxblood-red and near-black metal floor plates with riveted seams and a fine grating pattern, worn and scuffed. A flat pattern seen exactly from directly above, no perspective, even flat lighting, fills the whole square image edge to edge, no objects on it. No text, no symbols."),
    },
    "vulcan": {
        "stasis_unit": ("model", "A tall food stasis unit (a starship refrigerator): a slender upright bronze cabinet with a gently arched top, a single smooth ceramic door with a slim curved handle, and a small glowing teal status panel."),
        "bunk": ("model", "A two-tier bunk bed built into a bronze and sandstone wall unit with arched openings: two thin mattresses with red-brown woven blankets, a short slim ladder at one end, a soft teal light in each berth."),
        "arms_locker": ("model", "A tall narrow equipment locker standing against a wall: a bronze frame with a tall clear glass door, behind it a rack holding two slender staff-like instruments upright and a row of small hand-held devices on a shelf, a small teal status light."),
        "galley_range": ("model", "A compact starship galley cooking range, waist height: a bronze and sandstone cabinet with a flat dark stone cooktop with four softly glowing teal circles on top, an oven door with an arched dark glass window below, a row of small round controls."),
        "galley_sink": ("model", "A galley counter unit, waist height: a round bronze basin sink set into its sandstone worktop and a slender curved tap; smooth ceramic cabinet doors below."),
        "medical_cabinet": ("model", "A tall medical supply cabinet standing against a wall: a bronze and pale ceramic unit with frosted glass doors showing vials, instruments and folded cloths on its shelves, a small teal status light."),
        "bridge_chair": ("model", "A starship officer's seat: a high-backed chair with a tall tapered curved back in red-brown woven upholstery, a slim bronze frame, one armrest control panel, on a bronze pedestal."),
        "biobed": ("model", "A starship healer's medical bed, seen from its long side: a padded red-brown bed on a tapered bronze base, a curved display panel of teal lights at the head, and a slim arched bronze scanner frame over the chest area."),
        "tape_rack": ("model", "A tall open shelf rack that stands flat against a wall: a slim bronze frame with four shallow shelves holding rows of small rectangular data cartridges and one scroll case."),
        "tv_cabinet": ("model", "A low equipment cabinet, only knee height and as wide as it is deep: a bronze and sandstone chest with two small smooth doors on its front and a flat top."),
        "wall_sconce": ("flat", "A slim wall light of a Vulcan starship seen exactly front-on, flat, no perspective: a vertical tapered frosted panel glowing soft teal-white, in a slender burnished bronze mount with fine engraved lines. Centred, isolated on a plain flat light-grey background, even lighting, no cast shadow. No text, no symbols."),
        "science_display": ("flat", "A wide wall-mounted Vulcan starship science display screen seen exactly front-on, flat, no perspective: a dark screen showing an abstract star chart and flowing concentric circular diagrams in teal and soft gold, inside a thin burnished bronze bezel. The screen fills the whole image edge to edge. No text, no letters, no numbers, no symbols."),
        "wall": ("surface", "A flat, front-on texture of one section of a Vulcan starship's interior bulkhead wall. Smooth sandstone-coloured ceramic panels framed in burnished bronze, with fine engraved curved line patterns, a thin horizontal soft teal light strip about a third of the way down from the top, and a darker bronze kick plate along the bottom. A flat pattern: nothing mounted on it, nothing standing in front of it, no perspective, even flat lighting, the wall surface fills the whole image edge to edge. Slightly uneven hand-finished surface. No text, no symbols."),
        "deck": ("surface", "A flat texture of smooth floor tiles seen from directly above: dark reddish-brown polished stone squares with thin bronze-coloured lines between them in a simple repeating geometric pattern. Even flat lighting, no perspective, fills the whole square image edge to edge, nothing on it. No text."),
    },
}

# The size Starfleet's piece has, which is the size its stand-in is rendered at; and for the two
# Starfleet models in boxes, theirs.
# And the bunk: Starfleet's list says two squares deep and its tiles are one (fitted evenly it is
# that thin), so a stand-in for it is one square.
BOXES = {"bunk": dict(w=1, d=1, h=1.9, facings="WN"),
         "tape_rack": dict(w=1, d=1, h=1.94, facings="WN", layer="WallFurniture"),
         "tv_cabinet": dict(w=1, d=1, h=0.50, facings="WN", layer="Furniture")}


def piece(people, name):
    """One piece: its kind, its whole prompt, and what Starfleet's list says of the piece it stands in for."""
    kind, what = PIECES[people][name]
    theirs = A.by_name().get(name, {})
    out = dict(name=name, people=people, kind=kind, prompt=(STYLE[people] + what) if kind == "model" else what)
    if kind == "model":
        box = BOXES.get(name, theirs)
        out.update(w=box["w"], d=box["d"], h=box["h"], facings=box["facings"], layer=box.get("layer", "Furniture"))
    elif kind == "flat":
        out.update(u=theirs["u"], v=theirs["v"], layer="WallFurniture")
    return out


def pieces(people):
    return [piece(people, name) for name in PIECES[people]]
