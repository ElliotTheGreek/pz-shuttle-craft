"""Every object the Adirondack needs: the one list the art pipeline works from.

ADIRONDACK.md section 6 is the prose; this is the data. Each entry says what
the object is, how it gets made, how big it is, which ways it faces and what
the game should make of it.

kind
  model   a Gemini concept, turned into a mesh by fal (TRELLIS), rendered into
          tiles by tools/isorender.py from each facing
  reuse   one of the mod's own meshes (the replicator, the warp core...), same
          render
  flat    a Gemini texture laid on a wall face, like the LCARS display --
          anything that is a picture on a bulkhead needs no depth

size, in squares and world units (a storey is 2.449)
  w  along the wall it backs onto      d  out from that wall      h  height
  For something free-standing (a stool, a table), w and d are just its size.

facings
  "WN"    backs onto a west or a north wall -- the walls the camera sees, as
          vanilla's beds and wardrobes do
  "WNES"  all four, for things that turn (chairs, counters, consoles)
  "1"     looks the same every way (a round table, a plant)

use: what the tile definitions will say later -- container type, bed, seat,
light. Nothing reads it yet; it is written down now so it is not re-decided.
"""

STYLE = (
    "Product render of a single piece of furniture from the interior of a "
    "late-24th-century Starfleet starship, in the clean, calm style of the "
    "starship interiors of that era. Front view, seen straight on and slightly "
    "from above, the whole object in frame and centred, isolated on a plain "
    "flat light-grey background, soft even studio lighting, no cast shadow. "
    "Materials: warm light-grey and beige composite panels, dark charcoal "
    "trim, muted slate-blue upholstery, brushed metal, small soft amber light "
    "strips. No text, no numbers, no logos, no insignia, no people. "
)


def m(name, area, prompt, w, d, h, facings="WN", use=None):
    return dict(name=name, area=area, kind="model", prompt=STYLE + prompt,
                w=w, d=d, h=h, facings=facings, use=use or {})


def reuse(name, area, source, w, d, h, facings="WN", use=None):
    return dict(name=name, area=area, kind="reuse", source=source,
                w=w, d=d, h=h, facings=facings, use=use or {})


def flat(name, area, prompt, u=(0.15, 0.85), v=(0.15, 0.6), use=None):
    return dict(name=name, area=area, kind="flat", prompt=prompt, u=u, v=v,
                use=use or {})


OBJECTS = [
    # --- crew quarters -----------------------------------------------------
    m("bed_double", "quarters", "A low double bed: a charcoal plinth recessed "
      "under a warm-grey platform, a cream mattress, a slate-blue duvet folded "
      "back at the top, two pillows, a padded beige headboard with a thin amber "
      "light strip along its top edge.", 2, 2, 1.1, use={"bed": "goodBed"}),
    m("bunk", "quarters", "A two-tier bunk bed built into a beige wall unit: "
      "two cream mattresses with slate-blue blankets, a short ladder at one "
      "end, amber reading lights in each berth.", 1, 2, 1.9, use={"bed": "averageBed"}),
    m("nightstand", "quarters", "A small bedside cabinet, rounded corners, "
      "warm grey with one drawer and a tiny amber light on top.", 1, 1, 0.55,
      use={"container": "sidetable"}),
    m("desk", "quarters", "A writing desk with a curved front edge, warm grey "
      "top, charcoal legs, a slim desktop computer terminal with a colourful "
      "rounded-block screen and a PADD lying beside it.", 2, 1, 0.9,
      use={"container": "desk"}),
    m("desk_chair", "quarters", "An office desk chair: a single curved "
      "slate-blue padded seat and back on a charcoal swivel column and "
      "four-spoke base.", 1, 1, 1.0, facings="WNES", use={"seat": True}),
    m("sofa", "quarters", "A long low sofa with a gently curved back, "
      "slate-blue upholstery, beige side panels, two cushions.", 2, 1, 0.85,
      facings="WNES", use={"seat": True}),
    m("armchair", "quarters", "A single comfortable lounge armchair with a "
      "curved high back, slate-blue upholstery on a charcoal base.", 1, 1, 1.0,
      facings="WNES", use={"seat": True}),
    m("coffee_table", "quarters", "A low oval coffee table with a smoked "
      "glass top on a charcoal pedestal, a small sculpture on it.", 1, 1, 0.45,
      facings="1"),
    m("wardrobe", "quarters", "A tall slim wardrobe cabinet with two smooth "
      "beige doors, rounded edges, a thin amber light strip down the middle "
      "seam.", 1, 1, 2.0, use={"container": "wardrobe"}),
    m("display_shelf", "quarters", "A tall open display shelf unit with four "
      "shelves holding a few PADDs, a small model starship, alien sculptures "
      "and a plant.", 1, 1, 1.9, use={"container": "shelves"}),
    m("sonic_shower", "quarters", "A tall enclosed sonic shower cubicle: a "
      "rounded beige capsule with a frosted glass door and a ring of soft "
      "blue light at the top.", 1, 1, 2.2),
    m("wash_basin", "quarters", "A wall-mounted wash basin: a smooth oval "
      "white basin on a slim beige cabinet, a small mirror panel above.",
      1, 1, 1.6, use={"water": True}),
    m("toilet", "quarters", "A compact wall-hung starship toilet in white "
      "and grey with a beige wall panel behind it.", 1, 1, 0.9),
    m("plant", "quarters", "An exotic alien house plant with broad teal and "
      "purple leaves in a tall smooth white planter.", 1, 1, 1.4, facings="1"),

    # --- mess hall, lounge, galley ------------------------------------------
    m("bar_straight", "lounge", "A straight section of lounge bar counter: a "
      "smooth curved front in beige with an amber light strip along the "
      "bottom, a dark polished top.", 2, 1, 1.1, facings="WNES",
      use={"container": "counter"}),
    m("bar_corner", "lounge", "A curved corner section of lounge bar counter, "
      "a quarter circle: smooth beige front with an amber light strip along "
      "the bottom, a dark polished top.", 1, 1, 1.1, facings="WNES",
      use={"container": "counter"}),
    m("bar_stool", "lounge", "A tall bar stool: a round slate-blue cushioned "
      "seat on a slim charcoal column and round base.", 1, 1, 0.8, facings="1",
      use={"seat": True}),
    m("lounge_table", "lounge", "A round table for two, a white top on a "
      "flared charcoal pedestal.", 1, 1, 0.75, facings="1"),
    m("lounge_chair", "lounge", "A lounge chair with a curved slate-blue "
      "shell back and seat on four slim charcoal legs.", 1, 1, 0.95,
      facings="WNES", use={"seat": True}),
    m("bottle_shelf", "lounge", "A tall back-bar shelf unit with glowing amber "
      "backlit shelves holding rows of exotic alien bottles in many colours.",
      1, 1, 2.0, use={"container": "shelves"}),
    m("galley_counter", "lounge", "A galley kitchen counter unit: beige "
      "cabinet doors, a charcoal worktop, a thin amber light strip under the "
      "top.", 2, 1, 0.95, facings="WNES", use={"container": "counter"}),
    m("galley_sink", "lounge", "A galley kitchen counter unit with a sink set "
      "into its charcoal worktop and a curved tap; beige cabinet doors.",
      1, 1, 0.95, facings="WNES", use={"container": "counter", "water": True}),
    m("stasis_unit", "lounge", "A tall food stasis unit (a starship "
      "refrigerator): a smooth beige cabinet with a rounded top, a vertical "
      "handle and a small glowing blue status panel.", 1, 1, 2.0,
      use={"container": "fridge"}),

    # --- bridge ---------------------------------------------------------------
    m("captain_chair", "bridge", "A commanding starship captain's chair: a "
      "high-backed swivel seat in dark slate-blue leather with wide armrests "
      "that each hold a small colourful control panel, on a charcoal "
      "pedestal.", 1, 1, 1.25, facings="WNES", use={"seat": True}),
    m("bridge_chair", "bridge", "A starship bridge officer's seat: a "
      "high-backed swivel chair in slate-blue leather with one armrest "
      "control panel, on a charcoal pedestal.", 1, 1, 1.15, facings="WNES",
      use={"seat": True}),
    m("helm_console", "bridge", "A free-standing starship helm console: a "
      "low angled desk-height station with a wide sloping black control "
      "surface covered in colourful rounded-block touch panels, on a curved "
      "beige base.", 1, 1, 1.0, facings="WNES"),
    m("tactical_rail", "bridge", "A long curved starship tactical station "
      "rail: a waist-high curved beige rail whose sloped top is a strip of "
      "colourful rounded-block touch panels.", 2, 1, 1.1, facings="WNES"),
    m("science_station", "bridge", "A standing wall console for a starship "
      "science officer: a tall beige unit with an angled black touch surface "
      "of colourful rounded-block panels at waist height and a display above.",
      1, 1, 2.0),
    m("railing", "bridge", "A section of starship bridge railing: a smooth "
      "curved beige handrail on slim charcoal posts with an amber light strip "
      "underneath.", 1, 1, 1.0, facings="WNES"),
    m("ready_room_desk", "bridge", "A captain's ready-room desk: a wide "
      "polished dark desk with curved ends, a slim terminal screen, a "
      "starship model and a tea cup on it.", 2, 1, 0.9,
      use={"container": "desk"}),

    # --- sickbay --------------------------------------------------------------
    m("biobed", "sickbay", "A starship sickbay biobed: a padded grey bed "
      "on a beige base, with a curved diagnostic display panel of colourful "
      "rounded blocks at the head and a slim arched scanner frame over the "
      "chest area.", 1, 2, 1.6, use={"bed": "goodBed"}),
    m("surgical_bed", "sickbay", "A starship surgical bed: a padded grey "
      "operating table on a single central column, a large curved overhead "
      "surgical lamp arm with a ring of soft white light.", 1, 2, 1.9),
    m("medical_cabinet", "sickbay", "A tall wall-mounted starship medical "
      "supply cabinet: a smooth white and beige unit with frosted glass doors "
      "showing hyposprays and instruments, a small blue status light.",
      1, 1, 2.0, use={"container": "medicine"}),
    m("medical_cart", "sickbay", "A small wheeled medical instrument cart: a "
      "slim beige trolley with a tray of silver hyposprays and medical "
      "scanners on top.", 1, 1, 0.95, facings="WNES",
      use={"container": "medicine"}),

    # --- engineering ------------------------------------------------------------
    m("master_systems", "engineering", "A large rectangular starship master "
      "systems display table: a waist-high table whose whole top is a glowing "
      "black screen with a colourful cutaway schematic of a starship, on a "
      "beige base.", 2, 2, 1.1, facings="1"),
    m("engineering_console", "engineering", "A standing starship engineering "
      "console against a wall: a tall beige unit with a sloping black touch "
      "surface of orange and blue rounded-block panels and a tall display "
      "above.", 1, 1, 2.1),
    m("cargo_crate", "engineering", "A starship cargo container: a rugged "
      "rectangular crate in grey with rounded edges, reinforced corners, "
      "recessed handles and a small amber status light.", 1, 1, 0.9,
      facings="WNES", use={"container": "crate"}),
    m("antigrav_cart", "engineering", "An anti-gravity cargo sled: a flat "
      "grey hovering platform with a handle bar at one end, two small crates "
      "strapped on it, blue glowing emitters underneath.", 1, 1, 1.0,
      facings="WNES", use={"container": "crate"}),
    m("jefferies_hatch", "engineering", "A round Jefferies tube access hatch "
      "set in a beige wall panel: a grey circular door with a yellow and "
      "black safety rim and a small control pad beside it.", 1, 1, 1.6),

    # --- transporter room ---------------------------------------------------------
    m("transporter_pad", "transporter", "A starship transporter platform: a "
      "raised dais with six circular glowing transporter pads arranged in two "
      "rows of three, a curved front step, soft light panels in the ceiling "
      "piece above.", 3, 2, 2.3, facings="WN"),
    m("transporter_console", "transporter", "A starship transporter control "
      "console: a free-standing angled console with a black touch surface of "
      "colourful rounded-block panels and three sliding control strips, on a "
      "beige base.", 1, 1, 1.2, facings="WNES"),

    # --- the mod's own machines -------------------------------------------------
    reuse("replicator", "lounge", "TrekShuttle/42/media/models_X/TREK_Replicator.x",
          1, 1, 1.6, use={"replicator": True}),
    reuse("emh_station", "sickbay", "TrekShuttle/42/media/models_X/TREK_EMHStation.x",
          1, 1, 2.2, use={"emh": True}),
    reuse("warp_core", "engineering", "TrekShuttle/42/media/models_X/TREK_WarpCore.x",
          2, 2, 2.449, facings="1", use={"warpcore": True}),

    # --- pictures on bulkheads --------------------------------------------------
    flat("painting_ship", "any", "A framed painting in a slim dark frame: an "
         "original sleek fictional starship of a design you invent, flying "
         "past a ringed planet, painterly.", v=(0.18, 0.5)),
    flat("painting_nebula", "any", "A framed painting in a slim dark frame: "
         "a colourful nebula in deep space, painterly.", v=(0.18, 0.5)),
    flat("plaque", "any", "A small dedication plaque: a brushed bronze "
         "rectangle with an embossed abstract starship silhouette and "
         "decorative engraved lines, no readable text.", u=(0.3, 0.7), v=(0.25, 0.45)),
    flat("wall_sconce", "any", "A slim wall light: a vertical rounded "
         "frosted panel glowing warm white, in a beige mount.",
         u=(0.4, 0.6), v=(0.2, 0.5), use={"light": True}),
    flat("turbolift_panel", "any", "A small wall-mounted starship turbolift "
         "control panel: a black screen with a vertical column of colourful "
         "rounded-block buttons, no text.", u=(0.3, 0.7), v=(0.25, 0.55)),
    flat("science_display", "bridge", "A wide wall-mounted starship display "
         "showing an abstract star chart with colourful rounded-block "
         "interface frames, no text.", v=(0.15, 0.55)),
]


# --- hydroponics (FARMING.md) -----------------------------------------------------
# Appended, never inserted: the sheet is laid out in this order, and a built
# deck names its tiles by index, so everything above keeps its number.
OBJECTS += [
    m("hydro_tray", "hydroponics", "A single square raised hydroponic planter "
      "tray: a waist-low box of warm light-grey composite with rounded corners "
      "and a charcoal base, a thin soft amber light strip around its rim, "
      "filled almost to the top with dark crumbly growing medium. Empty, "
      "nothing planted in it.", 1, 1, 0.55, facings="1", use={"tray": True}),
    m("seed_locker", "hydroponics", "A narrow tall storage cabinet for seed "
      "packets: warm light-grey panels, a grid of small square drawers each "
      "with a soft green indicator light, charcoal trim.", 1, 1, 1.9,
      use={"container": "shelves"}),
    m("potting_bench", "hydroponics", "A long botanist's potting bench: a "
      "light-grey composite worktop over charcoal cabinets with doors, a "
      "small built-in sink basin at one end and a row of empty seed trays on "
      "the worktop, a slim amber light strip under the edge.", 2, 1, 0.95,
      use={"container": "counter"}),
    m("dehydrator", "hydroponics", "A starship food dehydrator cabinet: a "
      "waist-high light-grey box with a glass front door showing stacked "
      "mesh drying trays lit a warm amber inside, a small control panel of "
      "rounded coloured buttons beside the door.", 1, 1, 1.3,
      use={"container": "shelves"}),
    m("worm_tank", "hydroponics", "A long low glass-sided terrarium tank on a "
      "charcoal stand, half filled with dark wet earth, a few fat reddish "
      "serpent-like worms visible against the glass, a light-grey lid with "
      "small vents and a dim red indicator light.", 2, 1, 1.1,
      use={"container": "crate", "worms": True}),
    m("galley_range", "galley", "A compact starship galley cooking range: a "
      "light-grey cabinet with a flat black induction cooktop with four "
      "faintly glowing circles on top, an oven door with a dark glass window "
      "below, a strip of rounded coloured control buttons.", 1, 1, 0.95,
      facings="WNES", use={"stove": True}),
    m("arboretum_tree", "hydroponics", "A small ornamental tree in a round "
      "light-grey planter: a slender pale trunk and a rounded canopy of "
      "delicate blue-green leaves with tiny white blossoms.", 1, 1, 2.3,
      facings="1"),
    m("alien_shrub", "hydroponics", "A low alien ornamental shrub in a round "
      "light-grey planter: broad violet and teal leaves in a loose rosette, "
      "a few glowing pale seed pods.", 1, 1, 1.0, facings="1"),
    flat("grow_light", "hydroponics", "A long slim wall-mounted grow light "
         "panel in a light-grey frame, glowing a soft pink-violet.",
         u=(0.1, 0.9), v=(0.2, 0.35), use={"light": True}),
    # The cookware cupboard: a galley counter to look at (its mesh is a copy
    # of galley_counter's, tools/assets/adirondack/galley_cupboard.glb), and a
    # piece of its own so it can hold the pots rather than the food.
    m("galley_cupboard", "galley", "A galley kitchen counter unit: beige "
      "cabinet doors, a charcoal worktop, a thin amber light strip under the "
      "top.", 2, 1, 0.95, facings="WNES", use={"container": "counter"}),
]


def crop(name, prompt):
    """A crop (FARMING.md 2): one mesh of the mature plant, rendered at every
    growth stage by tools/gen_adirondack_crops.py -- not a piece of furniture."""
    return dict(name=name, area="crop", kind="crop", prompt=prompt)


OBJECTS += [
    crop("crop_tea", "tea bush (Camellia sinensis)"),
    crop("crop_bergamot", "bergamot orange bush"),
    crop("crop_klingon_coffee", "Klingon coffee shrub"),
    crop("crop_plomeek", "Vulcan plomeek"),
    crop("crop_leola", "Talaxian leola root"),
    crop("crop_andorian_tuber", "Andorian tuber"),
    crop("crop_hasperat", "Bajoran hasperat pepper"),
]


def by_name():
    return {o["name"]: o for o in OBJECTS}


if __name__ == "__main__":
    from collections import Counter
    print(len(OBJECTS), "objects;", dict(Counter(o["kind"] for o in OBJECTS)))
    for o in OBJECTS:
        print("%-20s %-12s %-6s %s" % (o["name"], o["area"], o["kind"],
              ("%sx%sx%s %s" % (o.get("w"), o.get("d"), o.get("h"), o.get("facings")))
              if o["kind"] != "flat" else ""))
