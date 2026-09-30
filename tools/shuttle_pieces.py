"""The shuttle's own two pieces of furniture, modelled in boxes.

The Starfleet refit of the shuttle's cabin (INTERIOR_REFIT.md) is built almost
entirely from the Adirondack's sheet. Two things it needs are not on it:

* **Lt. Shepard's tape rack** -- a slim wall-mounted rack over the deck beside
  the television, holding her VHS tapes. A wall object, so the square under
  it stays deck (vanilla's metal wall shelf is the shape it replaces).
* **The television's cabinet** -- a low Starfleet console her 1993 set
  stands on. It holds things, and its `Surface` is its own top, so the
  television (IsSurfaceOffset) is drawn sitting on it.

Both are simple enough to describe exactly, and a box model is the same
object from every facing by construction, so they are modelled here rather
than put through the concept-and-mesh pipeline. tools/gen_adirondack_furniture.py
renders them like the single bed.

Coordinates are the piece's own: `a` along the wall it backs onto (0..w),
`o` out from that wall into the room (0..d), `z` up, in world units (a storey
is 2.449). Each box is (a0, a1, o0, o1, z0, z1, colour).
"""

# The Adirondack's palette (adirondack_objects.STYLE): warm grey and beige
# composite, charcoal trim, brushed metal, small amber light strips.
CHARCOAL = (54, 56, 62)
TRIM = (84, 88, 96)
BEIGE = (186, 176, 160)
GREY = (164, 158, 150)
AMBER = (255, 206, 140)
CASE = (26, 26, 30)
LABEL = (226, 220, 204)
INK = ((226, 220, 204), (232, 198, 120), (180, 200, 226), (226, 220, 204),
       (214, 150, 120), (226, 220, 204))


def tape_rack():
    """Two shelves of tapes on a charcoal back plate, at eye height."""
    boxes = [
        (0.08, 0.92, 0.00, 0.03, 0.96, 1.94, CHARCOAL),     # back plate
        (0.08, 0.13, 0.03, 0.25, 1.00, 1.90, BEIGE),        # cheeks
        (0.87, 0.92, 0.03, 0.25, 1.00, 1.90, BEIGE),
        (0.13, 0.87, 0.03, 0.25, 1.00, 1.04, GREY),         # bottom shelf
        (0.13, 0.87, 0.03, 0.25, 1.44, 1.48, GREY),         # upper shelf
        (0.08, 0.92, 0.03, 0.26, 1.86, 1.90, BEIGE),        # top cap
        (0.13, 0.87, 0.245, 0.255, 1.405, 1.425, AMBER),    # light under each shelf
        (0.13, 0.87, 0.245, 0.255, 1.825, 1.845, AMBER),
    ]
    # The tapes stand on end, spines out, each with her handwritten label.
    for shelf, z0, count, gap in ((0, 1.04, 13, 9), (1, 1.48, 11, None)):
        a = 0.15
        for k in range(count):
            if gap is not None and k == gap:
                a += 0.06                                   # one out, being watched
            boxes.append((a, a + 0.046, 0.05, 0.20, z0, z0 + 0.21, CASE))
            ink = INK[(k + shelf * 2) % len(INK)]
            boxes.append((a + 0.008, a + 0.038, 0.20, 0.205, z0 + 0.05, z0 + 0.16, ink))
            a += 0.052
    return boxes


def tv_cabinet():
    """A low console with a dark top, two doors and a strip of amber."""
    return [
        (0.10, 0.90, 0.06, 0.50, 0.00, 0.06, CHARCOAL),     # plinth
        (0.05, 0.95, 0.03, 0.55, 0.06, 0.46, GREY),         # body
        (0.03, 0.97, 0.00, 0.58, 0.46, 0.50, TRIM),         # top
        (0.495, 0.505, 0.55, 0.556, 0.10, 0.40, CHARCOAL),  # the doors' seam
        (0.10, 0.90, 0.55, 0.556, 0.415, 0.43, AMBER),      # light strip
        (0.72, 0.88, 0.55, 0.556, 0.14, 0.20, (226, 150, 70)),   # a little LCARS
        (0.72, 0.82, 0.55, 0.556, 0.22, 0.27, (126, 152, 200)),
        (0.84, 0.88, 0.55, 0.556, 0.22, 0.27, (190, 150, 190)),
    ]


# Heights the tiledef needs: the top of the cabinet in 1x pixels, which is
# what a table's `Surface` is (fixtures_counters_01_35: 35 at 0.95 high).
TV_CABINET_TOP = 0.50
PX_PER_UNIT_1X = 96.0 / 2.449

PIECES = {"tape_rack": tape_rack, "tv_cabinet": tv_cabinet}
