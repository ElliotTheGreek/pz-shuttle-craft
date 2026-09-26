"""The Adirondack's Jefferies tubes: crawlways between her decks, and the hideouts off them.

Used by tools/gen_adirondack_lua.py; JEFFERIES.md is the guide.

Her decks stand side by side, DECK_PITCH squares apart, far enough that no deck
is ever loaded -- and so never drawn -- from another. A tube joins each deck to
the next *across that gap*: a crawlway one square wide, out through a hatch in
one deck's corridor and in through a hatch in the next one's, over the starfield
the whole way. Nobody is moved; the crew crawl it.

    deck k's corridor west wall, row OUT_Y  ->  north past the lift car
      -> east above the decks, in straight runs with turns north and south
      -> south at the far end  ->  deck k+1's corridor west wall, row IN_Y

The route is random and fixed: every tube has its own seed, so a regeneration
builds the same tube and a save never finds one moved under it.

**A tube is walled by the same rule as a deck** -- a wall on every edge between
a tube square and anything that is not the tube -- and that rule is why the
route must never touch itself. Two squares of one tube that share an edge
without being next to each other along it get no wall between them, and the
crawlway would open sideways into its own next leg. `check` refuses any such
pair, any two tubes that touch, and any tube square on a deck's own room.

**Hideouts.** Three tubes have one: a short side crawl off a straight run, a
hatch, and a small room where the off-watch crew have been meeting -- crates of
the good stuff, a table, cards, and the empties they never cleared away. The
room is the tube's too (walled with it), and one stands up in it.

Everything here is in the frame of the tube's own deck (`from`): x and y
relative to that deck's 0,0, so x runs on past its east edge into the gap.
"""
import random

DECK_PITCH = 108
# Rows of the corridor's west wall the hatches are on: out to the next deck,
# in from the previous one. The corridor runs from row 3 to its end; row 4
# carries the lift panel and row 6 the basin (compose_adirondack.py).
OUT_Y = 3
IN_Y = 5
# The band the crossing wanders in, north of the decks.
BAND = (-13, -3)
RUN = (5, 13)
JOG = (2, 5)
# Tubes that have a hideout, by index (0 = the tube from Deck 1 to Deck 2).
HIDEOUTS = (0, 2, 3)

S1 = "trek_adirondack_01_%d"
S2 = "trek_adirondack_02_%d"
TUBE_W, TUBE_N, TUBE_NW, TUBE_SE, TUBE_NDOOR = (S1 % i for i in (4, 5, 6, 7, 13))
BULK_W, BULK_N, BULK_NW, BULK_WDOOR = (S1 % i for i in (0, 1, 2, 10))
HATCH_W, HATCH_N = S1 % 36, S1 % 37
GRATING = S1 % 26
HIDEOUT_FLOOR = S1 % 25
# Under a tube wall that stands on a square outside the tube: a floor the
# engine counts and nobody sees (a wall on a square with no floor misbehaves).
UNDER_WALL = "invisible_01_0"


def route(n, W, H, pitch):
    """Tube n's crawlway, from its hatch outwards: a list of squares."""
    rnd = random.Random(1701 + 37 * n)
    x, y = -1, OUT_Y
    path = [(x, y)]
    while y > BAND[1]:
        y -= 1
        path.append((x, y))
    end_x = pitch - 4
    while x < end_x:
        run = min(rnd.randint(*RUN), end_x - x)
        for _ in range(run):
            x += 1
            path.append((x, y))
        if x >= end_x:
            break
        n_jog = rnd.randint(*JOG)
        d = rnd.choice((-1, 1))
        if not BAND[0] <= y + d * n_jog <= BAND[1]:
            d = -d
        to = max(BAND[0], min(BAND[1], y + d * n_jog))
        while y != to:
            y += 1 if to > y else -1
            path.append((x, y))
    while y < IN_Y:
        y += 1
        path.append((x, y))
    while x < pitch - 1:
        x += 1
        path.append((x, y))
    return path


def hideout_site(path, n):
    """A square in the middle of a straight run along the band, with nothing
    of the tube in the columns either side: the side crawl goes north from it.
    Which of the candidates is the tube's own seeded choice, so the hideouts
    are not all the same distance out."""
    sites = []
    for i in range(len(path) // 5, len(path) - 8):
        x, y = path[i]
        cols = [p for p in path if x - 3 <= p[0] <= x + 4]
        if cols and all(p[1] == y for p in cols) and y <= BAND[1] and len(cols) == 8:
            sites.append(i)
    if not sites:
        raise SystemExit("tube %d has no straight run long enough for a hideout" % n)
    return random.Random(4077 + n).choice(sites)


def piece(index, name, facing):
    """The squares of one piece of furniture, facing one way: [(dx, dy, sprite)]."""
    return [(dx, dy, S2 % i) for dx, dy, i in index[name]["facings"][facing]]


def hideout(path, i, index):
    """The side crawl, the room, its fittings and what was left lying about."""
    x, y = path[i]
    branch = [(x, y - 1), (x, y - 2)]
    x0, y0 = x - 1, y - 5
    room = [(x0 + dx, y0 + dy) for dy in range(3) for dx in range(4)]
    fittings = []

    def put(name, facing, px, py, stash=None):
        kind = "c" if "container" in index[name].get("use", {}) else "f"
        for dx, dy, s in piece(index, name, facing):
            fittings.append((px + dx, py + dy, s, stash or name, kind))

    put("cargo_crate", "W", x0, y0, "stash_crate")
    put("bottle_shelf", "N", x0 + 2, y0, "stash_shelf")
    put("cargo_crate", "E", x0 + 3, y0, "stash_crate")
    put("lounge_table", "W", x0 + 2, y0 + 1)
    put("lounge_chair", "W", x0 + 1, y0 + 1)
    put("lounge_chair", "E", x0 + 3, y0 + 1)
    put("wall_sconce", "N", x0 + 1, y0)
    # What the night watch left: bottles and cans on the deck, the cards on
    # the table. Placed once, as world items (TREK_AdirondackServer).
    clutter = [(x0, y0 + 1, "Base.BeerEmpty"), (x0, y0 + 2, "Base.BeerEmpty"),
               (x0 + 3, y0 + 2, "Base.BeerCanEmpty"), (x0 + 2, y0 + 2, "Base.BeerEmpty"),
               (x0 + 2, y0 + 1, "Base.CardDeck"), (x0 + 2, y0 + 1, "Base.PokerChips"),
               (x0 + 1, y0 + 2, "Base.BeerCanEmpty"), (x0 + 3, y0 + 1, "Base.BeerEmpty")]
    return dict(branch=branch, room=room, door=(x, y - 2), fittings=fittings, clutter=clutter)


def check(tubes, decks, pitch):
    """Refuse a tube that would be built without a wall where one belongs."""
    # In one frame, deck 1's, so tubes can be compared with each other.
    owner = {}
    for t in tubes:
        for x, y in t["squares"]:
            g = (x + t["n"] * pitch, y)
            if g in owner:
                raise SystemExit("tubes %d and %d share %s" % (owner[g], t["n"], g))
            owner[g] = t["n"]
    for t in tubes:
        n, squares, opens = t["n"], set(t["squares"]), t["open"]
        for (x, y) in squares:
            for other in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if other in squares:
                    if frozenset(((x, y), other)) not in opens:
                        raise SystemExit("tube %d touches itself at %s and %s: there would be no "
                                         "wall between them" % (n, (x, y), other))
                    continue
                g = (other[0] + n * pitch, other[1])
                if owner.get(g, n) != n:
                    raise SystemExit("tube %d touches tube %d at %s" % (n, owner[g], (x, y)))
            for k in (n, n + 1):
                gx, gy = x - (k - n) * pitch, y
                grid = decks[k]["grid"]
                if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]) and grid[gy][gx]:
                    raise SystemExit("tube %d runs over a room of deck %d at %s" % (n, k + 1, (x, y)))


def walls(t, deck_room):
    """The tube's walls, by the decks' rule: [(x, y, sprite)], and the squares
    outside the tube that one of them stands on."""
    T = set(t["squares"])
    opens = t["open"]

    def solid(a, b):
        """True when the edge between squares a and b needs a tube wall."""
        ia, ib = a in T, b in T
        if ia and ib:
            return frozenset((a, b)) not in opens
        if not (ia or ib):
            return False
        other = b if ia else a
        return not deck_room(*other)          # a deck walls its own rooms

    xs = [p[0] for p in T]
    ys = [p[1] for p in T]
    out, outside = [], set()
    for y in range(min(ys), max(ys) + 2):
        for x in range(min(xs), max(xs) + 2):
            if deck_room(x, y) and (x, y) not in T:
                continue
            west = solid((x - 1, y), (x, y))
            north = solid((x, y - 1), (x, y))
            s = None
            if west and north:
                s = TUBE_NW
            elif west:
                s = TUBE_W
            elif north:
                s = TUBE_N
            elif solid((x - 1, y - 1), (x, y - 1)) and solid((x - 1, y - 1), (x - 1, y)):
                # The corner post where a wall from the north meets one from the
                # west and neither carries on across this square.
                s = TUBE_SE
            if s:
                out.append((x, y, s))
                if (x, y) not in T:
                    outside.add((x, y))
    return out, outside


def build(decks, W, H, index, pitch=DECK_PITCH):
    """Every tube between consecutive decks. `decks` in deck order, each with
    `grid`, `structure` and `floors`; each deck's hatches are added to its own
    structure (they are on its corridor wall). Returns the tubes."""
    tubes = []
    for n in range(len(decks) - 1):
        path = route(n, W, H, pitch)
        opens = {frozenset(pr) for pr in zip(path, path[1:])}
        t = dict(n=n, path=path, crawl=list(path), squares=list(path), open=opens,
                 floors={p: GRATING for p in path}, objects=[], clutter=[], hideout=None)
        if n in HIDEOUTS:
            i = hideout_site(path, n)
            h = hideout(path, i, index)
            chain = [path[i]] + h["branch"]
            opens |= {frozenset(pr) for pr in zip(chain, chain[1:])}
            opens.add(frozenset((h["branch"][-1], (h["door"][0], h["door"][1] - 1))))
            room = set(h["room"])
            for (x, y) in room:
                for o in ((x + 1, y), (x, y + 1)):
                    if o in room:
                        opens.add(frozenset(((x, y), o)))
            t["squares"] += h["branch"] + h["room"]
            t["crawl"] += h["branch"]
            t["door"] = h["door"]
            t["hideout"] = h["room"]
            for p in h["branch"]:
                t["floors"][p] = GRATING
            for p in h["room"]:
                t["floors"][p] = HIDEOUT_FLOOR
            t["objects"] += [(h["door"][0], h["door"][1], TUBE_NDOOR, "w"),
                             (h["door"][0], h["door"][1], HATCH_N, "dN")]
            for x, y, s, what, kind in h["fittings"]:
                t["objects"].append((x, y, s, kind, what))
            t["clutter"] = h["clutter"]
        tubes.append(t)

    check(tubes, decks, pitch)

    for t in tubes:
        n = t["n"]

        def deck_room(x, y, n=n):
            for k in (n, n + 1):
                gx = x - (k - n) * pitch
                grid = decks[k]["grid"]
                if 0 <= y < len(grid) and 0 <= gx < len(grid[0]) and grid[y][gx]:
                    return True
            return False

        wall_list, outside = walls(t, deck_room)
        t["objects"] = [(x, y, s, "w") for x, y, s in wall_list] + t["objects"]
        for p in outside:
            if deck_room(*p) or p in decks[n]["floors"] or (p[0] - pitch, p[1]) in decks[n + 1]["floors"]:
                continue
            t["floors"].setdefault(p, UNDER_WALL)

    # The hatches, on the decks' own corridor walls: a doorway where the wall
    # was, and the hatch in it.
    for k, deck in enumerate(decks):
        rows = ([OUT_Y] if k < len(decks) - 1 else []) + ([IN_Y] if k > 0 else [])
        for y in rows:
            here = [o for o in deck["structure"] if o[0] == 0 and o[1] == y and o[3] == "w"]
            if len(here) != 1 or here[0][2] not in (BULK_W, BULK_NW):
                raise SystemExit("deck %d: no plain corridor wall at 0,%d for a tube hatch: %s"
                                 % (k + 1, y, here))
            deck["structure"].remove(here[0])
            if here[0][2] == BULK_NW:
                deck["structure"].append((0, y, BULK_N, "w"))
            deck["structure"].append((0, y, BULK_WDOOR, "w"))
            deck["structure"].append((0, y, HATCH_W, "dW"))
    return tubes


def span(tubes, W, H, count, pitch=DECK_PITCH):
    """Every square of the ship, decks and tubes, relative to deck 1's 0,0."""
    xs = [0, (count - 1) * pitch + W - 1]
    ys = [0, H - 1]
    for t in tubes:
        for x, y in t["squares"]:
            xs.append(x + t["n"] * pitch)
            ys.append(y)
    return min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1
