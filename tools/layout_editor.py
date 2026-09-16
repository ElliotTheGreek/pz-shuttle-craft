#!/usr/bin/env python3
"""Visual editor for literal fit/line/place calls in a PZ Lua builder."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD = ROOT / "TrekShuttle/42/media/lua/client/TREK/TREK_Build.lua"
DEFAULT_CATALOG = ROOT / "tools/_catalog/tiles.json"
CALL_RE = re.compile(r"\b(fit|line|place)\s*\(([^\n)]*)\)")
INT_RE = re.compile(r"^-?\d+$")
CELL = 58


def split_args(text):
    result, start, quote, escaped, depth = [], 0, None, False, 0
    for i, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            result.append(text[start:i].strip())
            start = i + 1
    result.append(text[start:].strip())
    return result


def unquote(value):
    value = value.strip()
    return value[1:-1] if len(value) > 1 and value[0] in "\"'" and value[-1] == value[0] else value


class Placement:
    def __init__(self, line, match, kind, args):
        self.line, self.start, self.end = line, match.start(), match.end()
        self.kind, self.args = kind, args

    @property
    def x(self): return int(self.args[0])
    @property
    def y(self): return int(self.args[1])
    @property
    def sprite_index(self): return 4 if self.kind == "line" else 2
    @property
    def sprite(self): return unquote(self.args[self.sprite_index])

    def cells(self):
        if self.kind != "line" or not INT_RE.match(self.args[2]) or not INT_RE.match(self.args[3]):
            return [(self.x, self.y)]
        x2, y2 = int(self.args[2]), int(self.args[3])
        dx, dy = (x2 > self.x) - (x2 < self.x), (y2 > self.y) - (y2 < self.y)
        return [(self.x + dx*n, self.y + dy*n) for n in range(max(abs(x2-self.x), abs(y2-self.y)) + 1)]


class Layout:
    def __init__(self, path):
        self.path = path
        self.load()

    def load(self):
        self.lines = self.path.read_text(encoding="utf-8").splitlines(keepends=True)
        self.parse()

    def parse(self):
        self.items = []
        for number, line in enumerate(self.lines):
            match = CALL_RE.search(line)
            if not match:
                continue
            kind, args = match.group(1), split_args(match.group(2))
            minimum = 5 if kind == "line" else 3
            if len(args) >= minimum and INT_RE.match(args[0]) and INT_RE.match(args[1]):
                self.items.append(Placement(number, match, kind, args))

    def update(self, item):
        old = self.lines[item.line]
        call = item.kind + "(" + ", ".join(item.args) + ")"
        self.lines[item.line] = old[:item.start] + call + old[item.end:]
        self.parse()

    def save(self):
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        shutil.copy2(self.path, backup)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text("".join(self.lines), encoding="utf-8")
        temp.replace(self.path)
        self.load()
        return backup

    def overlaps(self):
        cells = {}
        for item in self.items:
            for cell in item.cells(): cells.setdefault(cell, []).append(item)
        return {cell: values for cell, values in cells.items() if len(values) > 1}


class Catalog:
    def __init__(self, path):
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.tiles = data.get("tiles", {})
        self.names = sorted(self.tiles)

    def search(self, text):
        words = text.lower().split()
        return [name for name in self.names if all(word in name.lower() for word in words)][:300]


class Editor(tk.Tk):
    def __init__(self, layout, catalog):
        super().__init__()
        self.layout, self.catalog, self.selected = layout, catalog, None
        self.title("PZ Interior Editor — " + layout.path.name)
        self.geometry("1280x800")
        self.make_ui()
        self.refresh()

    def make_ui(self):
        top = ttk.Frame(self, padding=6); top.pack(fill=tk.X)
        ttk.Button(top, text="Save Lua", command=self.save).pack(side=tk.LEFT)
        ttk.Button(top, text="Reload", command=self.reload).pack(side=tk.LEFT, padx=5)
        self.status = ttk.Label(top); self.status.pack(side=tk.RIGHT)
        panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL); panes.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(panes, padding=5); panes.add(left, weight=1)
        self.listbox = tk.Listbox(left, width=40, exportselection=False); self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.pick)
        self.canvas = tk.Canvas(panes, bg="#182127"); panes.add(self.canvas, weight=3)
        self.canvas.bind("<Button-1>", self.canvas_pick)
        right = ttk.Frame(panes, padding=7); panes.add(right, weight=2)
        ttk.Label(right, text="Complete Lua arguments").pack(anchor=tk.W)
        self.args = tk.Text(right, height=5, wrap=tk.WORD); self.args.pack(fill=tk.X)
        ttk.Button(right, text="Apply", command=self.apply).pack(anchor=tk.E, pady=4)
        ttk.Label(right, text="Sprite search").pack(anchor=tk.W)
        self.query = tk.StringVar(); entry = ttk.Entry(right, textvariable=self.query); entry.pack(fill=tk.X)
        entry.bind("<KeyRelease>", lambda _e: self.fill_sprites())
        self.sprites = tk.Listbox(right, exportselection=False); self.sprites.pack(fill=tk.BOTH, expand=True)
        self.sprites.bind("<Double-Button-1>", self.use_sprite)
        self.details = ttk.Label(right, wraplength=340); self.details.pack(fill=tk.X)
        self.sprites.bind("<<ListboxSelect>>", self.show_details)

    def bounds(self):
        cells = [c for item in self.layout.items for c in item.cells()]
        if not cells: return -6, 6, -6, 6
        xs, ys = [c[0] for c in cells], [c[1] for c in cells]
        return min(xs)-2, max(xs)+2, min(ys)-2, max(ys)+2

    def xy(self, x, y):
        minx, _, miny, _ = self.bounds()
        return (x-minx)*CELL + CELL//2, (y-miny)*CELL + CELL//2

    def refresh(self, selected_line=None):
        self.listbox.delete(0, tk.END)
        for item in self.layout.items:
            self.listbox.insert(tk.END, f"L{item.line+1} {item.kind}({item.x},{item.y}) {item.sprite}")
        self.draw(); self.fill_sprites()
        overlaps = self.layout.overlaps()
        self.status.config(text=f"{len(self.layout.items)} placements; {len(overlaps)} overlapping cells")
        if selected_line is not None:
            for i, item in enumerate(self.layout.items):
                if item.line == selected_line:
                    self.listbox.selection_set(i); self.select(i); break

    def draw(self):
        self.canvas.delete("all"); self.hit = {}
        minx, maxx, miny, maxy = self.bounds()
        self.canvas.config(scrollregion=(0, 0, (maxx-minx+1)*CELL, (maxy-miny+1)*CELL))
        overlaps = self.layout.overlaps()
        for x in range(minx, maxx+1):
            for y in range(miny, maxy+1):
                cx, cy = self.xy(x,y)
                self.canvas.create_rectangle(cx-CELL//2,cy-CELL//2,cx+CELL//2,cy+CELL//2,fill="#2b3b44",outline="#526b77")
                self.canvas.create_text(cx-CELL//2+3,cy-CELL//2+3,text=f"{x},{y}",anchor=tk.NW,fill="#9badb5",font=("TkDefaultFont",7))
        for item in self.layout.items:
            for cell in item.cells():
                cx, cy = self.xy(*cell)
                color = "#db615b" if cell in overlaps else ("#f1c75b" if item is self.selected else "#53a9aa")
                shape = self.canvas.create_rectangle(cx-21,cy-16,cx+21,cy+16,fill=color,outline="white")
                self.hit[shape] = item
            cx, cy = self.xy(*item.cells()[0]); self.canvas.create_text(cx,cy,text=item.sprite[-12:],width=43,font=("TkDefaultFont",7))

    def pick(self, _event=None):
        chosen = self.listbox.curselection()
        if chosen: self.select(chosen[0])

    def select(self, index):
        self.selected = self.layout.items[index]
        self.args.delete("1.0", tk.END); self.args.insert("1.0", ", ".join(self.selected.args)); self.draw()

    def canvas_pick(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for shape in reversed(self.canvas.find_overlapping(x-2,y-2,x+2,y+2)):
            if shape in self.hit:
                index = self.layout.items.index(self.hit[shape]); self.listbox.selection_clear(0,tk.END)
                self.listbox.selection_set(index); self.select(index); return

    def apply(self):
        if not self.selected: return
        args = split_args(self.args.get("1.0", tk.END).strip())
        minimum = 5 if self.selected.kind == "line" else 3
        if len(args) < minimum or not INT_RE.match(args[0]) or not INT_RE.match(args[1]):
            messagebox.showerror("Invalid", "Use literal integer x/y coordinates and keep all required arguments."); return
        self.selected.args = args; line = self.selected.line; self.layout.update(self.selected); self.selected = None; self.refresh(line)

    def fill_sprites(self):
        self.sprites.delete(0, tk.END)
        for name in self.catalog.search(self.query.get()): self.sprites.insert(tk.END, name)

    def use_sprite(self, _event=None):
        if not self.selected or not self.sprites.curselection(): return
        self.selected.args[self.selected.sprite_index] = '"' + self.sprites.get(self.sprites.curselection()[0]) + '"'
        self.args.delete("1.0",tk.END); self.args.insert("1.0",", ".join(self.selected.args))

    def show_details(self, _event=None):
        if not self.sprites.curselection(): return
        name = self.sprites.get(self.sprites.curselection()[0]); props = self.catalog.tiles.get(name,{})
        self.details.config(text=", ".join(f"{k}={v}" for k,v in list(props.items())[:8]))

    def save(self):
        backup = self.layout.save(); self.selected = None; self.refresh()
        messagebox.showinfo("Saved", f"Saved Lua. Backup: {backup}\nRun python tests/test_layout.py")

    def reload(self): self.layout.load(); self.selected = None; self.refresh()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build", nargs="?", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.build.exists(): parser.error(f"not found: {args.build}")
    layout, catalog = Layout(args.build.resolve()), Catalog(args.catalog.resolve())
    if args.check:
        print(f"Parsed {len(layout.items)} placements; loaded {len(catalog.names)} sprites")
        for cell, values in sorted(layout.overlaps().items()): print("OVERLAP", cell, [v.sprite for v in values])
        return 1 if layout.overlaps() else 0
    Editor(layout, catalog).mainloop(); return 0


if __name__ == "__main__": raise SystemExit(main())
