"""Reja va 3D: uy, do'kon, kafe, ofis uchun konsept reja.

Natija (hammasi outbox orqali foydalanuvchiga yuboriladi):
- .dxf  - AutoCAD/ArchiCAD/CorelDraw ochadi (mm, qatlamlar: devor, eshik, deraza, mebel, o'lcham, matn, harakat)
- _reja.png - chiroyli ko'rinish (xonalar, maydonlar, mebel, o'lchamlar, masshtab)
- .obj + .mtl - 3ds Max / Blender / SketchUp'ga import (metr, Y-yuqori)
- _3d.png - izometrik 3D ko'rinish (devorlar kesimda, ichki jihozlar ko'rinadi)
Bu konsept: aniq loyiha uchun joyida o'lchash va me'mor tekshiruvi kerak.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .. import outbox
from . import skill

# ------------------------------------------------------------------ ma'lumotlar
ROOM_COLORS = {
    "living": "#F6E7C8", "bedroom": "#DCE8F7", "kids": "#E3F2DC", "kitchen": "#FBE0D0", "bath": "#D6EFF2",
    "wc": "#D6EFF2", "hall": "#ECE7E1", "corridor": "#ECE7E1", "storage": "#E6E2EE", "office": "#E8EEDB",
    "hall_sales": "#FFF4D6", "fitting": "#F3DDF0", "cafe_hall": "#FFF0DA", "dining": "#FFF0DA", "balcony": "#E2F0E8",
}
ROOM_NAMES = {
    "uz": {"living": "Mehmonxona", "bedroom": "Yotoqxona", "kids": "Bolalar xonasi", "kitchen": "Oshxona",
           "bath": "Hammom", "wc": "Hojatxona", "hall": "Dahliz", "corridor": "Yo'lak", "storage": "Omborxona",
           "office": "Kabinet", "hall_sales": "Savdo zali", "fitting": "Kiyinish xonasi", "cafe_hall": "Zal",
           "dining": "Ovqatlanish", "balcony": "Balkon"},
    "ru": {"living": "Гостиная", "bedroom": "Спальня", "kids": "Детская", "kitchen": "Кухня", "bath": "Ванная",
           "wc": "Санузел", "hall": "Прихожая", "corridor": "Коридор", "storage": "Кладовая", "office": "Кабинет",
           "hall_sales": "Торговый зал", "fitting": "Примерочная", "cafe_hall": "Зал", "dining": "Столовая",
           "balcony": "Балкон"},
}
# (eni, chuqurligi, balandligi m, rangi, nomi)
FURNITURE = {
    "sofa": (2.2, 0.9, 0.85, "#8D99AE", "Divan"), "armchair": (0.85, 0.85, 0.85, "#8D99AE", "Kreslo"),
    "coffee_table": (1.1, 0.6, 0.45, "#C9A27E", "Stolcha"), "tv": (1.8, 0.45, 0.6, "#4A4E69", "TV"),
    "bed_double": (1.6, 2.0, 0.55, "#B8C5D6", "Karavot"), "bed_single": (0.9, 2.0, 0.55, "#B8C5D6", "Karavot"),
    "nightstand": (0.5, 0.4, 0.5, "#C9A27E", ""), "wardrobe": (1.8, 0.6, 2.2, "#A68A64", "Shkaf"),
    "desk": (1.2, 0.6, 0.75, "#C9A27E", "Stol"), "counter": (2.4, 0.6, 0.9, "#9C6644", "Oshxona"),
    "fridge": (0.7, 0.7, 1.9, "#E0E1DD", "Muzlatkich"), "dining": (1.2, 0.8, 0.75, "#C9A27E", "Stol"),
    "bathtub": (1.7, 0.75, 0.6, "#FFFFFF", "Vanna"), "shower": (0.9, 0.9, 2.0, "#FFFFFF", "Dush"),
    "sink": (0.6, 0.45, 0.85, "#FFFFFF", "Rakovina"), "toilet": (0.4, 0.65, 0.75, "#FFFFFF", "Unitaz"),
    "washer": (0.6, 0.6, 0.85, "#E0E1DD", "Kir mashina"), "shoe_rack": (1.2, 0.4, 1.0, "#A68A64", "Poyabzal"),
    "shelf": (1.0, 0.5, 2.0, "#E9C46A", "Javon"), "gondola": (2.4, 0.9, 1.6, "#F4A261", "Gondola"),
    "cashier": (1.6, 0.7, 1.0, "#2A9D8F", "Kassa"), "rack": (1.5, 0.6, 1.6, "#E76F51", "Kiyim ilgich"),
    "table4": (0.8, 0.8, 0.75, "#C9A27E", "Stol"), "bar": (3.0, 0.6, 1.1, "#9C6644", "Bar"),
    "storage_rack": (2.0, 0.6, 2.2, "#B5A47E", "Stellaj"), "mirror": (1.0, 0.1, 2.0, "#BEE3F8", "Oyna"),
    "showcase": (1.5, 0.6, 1.0, "#90E0EF", "Vitrina"), "chair": (0.42, 0.42, 0.45, "#8D6E63", ""),
}
WALL_EXT, WALL_INT, DOOR_H, SILL, WIN_TOP = 0.38, 0.12, 2.1, 0.9, 2.1


@dataclass
class Room:
    kind: str
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    furniture: list = field(default_factory=list)  # (type, x0, y0, x1, y1)

    @property
    def area(self):
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0


@dataclass
class Opening:
    kind: str       # door / entrance / window
    horizontal: bool
    a: float        # boshlanishi (o'q bo'yicha)
    b: float        # oxiri
    c: float        # devor koordinatasi (gorizontal - y, vertikal - x)
    room: Room | None = None


# ------------------------------------------------------------------ joylashtirish
def _squarify(items: list[tuple[str, float]], x0, y0, x1, y1) -> list[tuple[str, tuple]]:
    """Squarified treemap: xonalarni to'g'ri to'rtburchakka kvadratga yaqin qilib joylaydi."""
    out = []
    items = sorted(items, key=lambda kv: -kv[1])
    total = sum(a for _, a in items) or 1
    scale = (x1 - x0) * (y1 - y0) / total
    items = [(k, a * scale) for k, a in items]

    def worst(row, side):
        s = sum(a for _, a in row)
        return max(max(side * side * a / (s * s), s * s / (side * side * a)) for _, a in row)

    while items:
        w, h = x1 - x0, y1 - y0
        side = min(w, h)
        row = [items.pop(0)]
        while items and worst(row + [items[0]], side) <= worst(row, side):
            row.append(items.pop(0))
        s = sum(a for _, a in row)
        if w >= h:  # chap ustun
            cw = s / h
            y = y0
            for k, a in row:
                rh = a / cw
                out.append((k, (x0, y, x0 + cw, y + rh)))
                y += rh
            x0 += cw
        else:  # pastki qator
            rh = s / w
            x = x0
            for k, a in row:
                cw = a / rh
                out.append((k, (x, y0, x + cw, y0 + rh)))
                x += cw
            y0 += rh
    return out


def default_program(purpose: str, area: float, shop_kind: str) -> list[tuple[str, float]]:
    if purpose == "shop":
        prog = [("hall_sales", .76), ("storage", .14), ("wc", .04), ("office", .06)]
        if shop_kind == "clothing":
            prog = [("hall_sales", .78), ("storage", .12), ("wc", .04), ("fitting", .06)]
    elif purpose == "cafe":
        prog = [("cafe_hall", .62), ("kitchen", .22), ("storage", .07), ("wc", .09)]
    elif purpose == "office":
        prog = [("office", .62), ("office", .18), ("hall", .1), ("wc", .05), ("kitchen", .05)]
    elif area < 45:
        prog = [("living", .46), ("kitchen", .22), ("bath", .12), ("hall", .2)]
    elif area < 75:
        prog = [("living", .3), ("bedroom", .22), ("kitchen", .17), ("bath", .08), ("wc", .04), ("hall", .19)]
    elif area < 115:
        prog = [("living", .26), ("bedroom", .17), ("kids", .14), ("kitchen", .14), ("bath", .07), ("wc", .03),
                ("hall", .14), ("storage", .05)]
    else:
        prog = [("living", .24), ("bedroom", .15), ("kids", .12), ("bedroom", .11), ("kitchen", .12), ("bath", .06),
                ("wc", .03), ("hall", .12), ("office", .05)]
    return [(k, area * p) for k, p in prog]


def _shared(a: Room, b: Room):
    """Ikki xonaning umumiy devori: (horizontal, start, end, coord) yoki None."""
    eps = 1e-6
    for ya, yb in ((a.y1, b.y0), (a.y0, b.y1)):
        if abs(ya - yb) < eps:
            s, e = max(a.x0, b.x0), min(a.x1, b.x1)
            if e - s > eps:
                return True, s, e, ya
    for xa, xb in ((a.x1, b.x0), (a.x0, b.x1)):
        if abs(xa - xb) < eps:
            s, e = max(a.y0, b.y0), min(a.y1, b.y1)
            if e - s > eps:
                return False, s, e, xa
    return None


class Plan:
    def __init__(self, title, purpose, width, length, rooms, lang="uz", shop_kind="grocery", ceiling=2.8):
        self.title, self.purpose, self.W, self.L = title, purpose, width, length
        self.lang, self.shop_kind, self.ceiling = lang, shop_kind, ceiling
        self.rooms: list[Room] = rooms
        self.openings: list[Opening] = []
        self.flow: list[tuple[float, float]] = []
        self.zones: list[tuple[str, float, float]] = []  # (izoh, x, y)
        self.notes: list[str] = []

    # -- eshik va derazalar
    def place_openings(self):
        hubs = [r for r in self.rooms if r.kind in ("hall", "corridor", "hall_sales", "cafe_hall")] or \
               [max(self.rooms, key=lambda r: r.area)]
        hub = max(hubs, key=lambda r: r.area)
        connected, queue = {id(hub)}, [hub]
        while queue:
            cur = queue.pop(0)
            for other in sorted(self.rooms, key=lambda r: -r.area):
                if id(other) in connected:
                    continue
                edge = _shared(cur, other)
                if not edge or edge[2] - edge[1] < 1.0:
                    continue
                horizontal, s, e, c = edge
                width = 0.7 if other.kind in ("bath", "wc", "storage", "fitting") else 0.9
                mid = (s + e) / 2 if e - s < 2.4 else s + 0.35 + width / 2
                self.openings.append(Opening("door", horizontal, mid - width / 2, mid + width / 2, c, other))
                connected.add(id(other))
                queue.append(other)
        for r in self.rooms:  # bog'lanmagan xona - eng katta qo'shnisiga
            if id(r) in connected:
                continue
            best = max((x for x in self.rooms if x is not r and _shared(r, x)), key=lambda x: _shared(r, x)[2] - _shared(r, x)[1], default=None)
            if best:
                horizontal, s, e, c = _shared(r, best)
                mid = (s + e) / 2
                self.openings.append(Opening("door", horizontal, mid - .35, mid + .35, c, r))
        # Kirish eshigi: hub'ning tashqi devori (pastki devor afzal - ko'cha tomoni)
        entrance = 1.2 if self.purpose in ("shop", "cafe") else 1.0
        for side in (("bottom", "left", "right", "top") if self.purpose in ("shop", "cafe") else ("left", "right", "bottom", "top")):
            seg = self._exterior(hub, side)
            if seg and seg[1] - seg[0] >= entrance + 0.3:
                horizontal, c = side in ("bottom", "top"), (0 if side in ("bottom", "left") else (self.L if side == "top" else self.W))
                mid = (seg[0] + seg[1]) / 2
                self.openings.append(Opening("entrance", horizontal, mid - entrance / 2, mid + entrance / 2, c, hub))
                self.entrance_side, self.entrance_mid = side, mid
                break
        # Derazalar
        for r in self.rooms:
            if r.kind in ("bath", "wc", "storage", "hall", "corridor", "fitting"):
                continue
            sides = sorted(("bottom", "top", "left", "right"), key=lambda sd: -((self._exterior(r, sd) or (0, 0))[1] - (self._exterior(r, sd) or (0, 0))[0]))
            count = 0
            for side in sides:
                seg = self._exterior(r, side)
                if not seg or seg[1] - seg[0] < 1.2:
                    continue
                busy = [o for o in self.openings if o.kind == "entrance" and o.horizontal == (side in ("bottom", "top"))
                        and abs(o.c - (0 if side in ("bottom", "left") else (self.L if side == "top" else self.W))) < 1e-6
                        and o.b > seg[0] and o.a < seg[1]]
                length = seg[1] - seg[0]
                win = min(2.4 if r.kind in ("hall_sales", "cafe_hall") else 1.5, length * .5)
                mid = (seg[0] + seg[1]) / 2
                if busy:
                    o = busy[0]
                    left, right = o.a - seg[0], seg[1] - o.b
                    if max(left, right) < win + 0.6:
                        continue
                    mid = (seg[0] + o.a) / 2 if left > right else (o.b + seg[1]) / 2
                c = 0 if side in ("bottom", "left") else (self.L if side == "top" else self.W)
                self.openings.append(Opening("window", side in ("bottom", "top"), mid - win / 2, mid + win / 2, c, r))
                count += 1
                if count >= (2 if r.area > 18 else 1):
                    break

    def _exterior(self, r: Room, side: str):
        eps = 1e-6
        if side == "bottom" and r.y0 < eps:
            return r.x0, r.x1
        if side == "top" and abs(r.y1 - self.L) < eps:
            return r.x0, r.x1
        if side == "left" and r.x0 < eps:
            return r.y0, r.y1
        if side == "right" and abs(r.x1 - self.W) < eps:
            return r.y0, r.y1
        return None

    # -- mebel
    def _free(self, r: Room, box, taken):
        x0, y0, x1, y1 = box
        m = 0.05
        if x0 < r.x0 + m or y0 < r.y0 + m or x1 > r.x1 - m or y1 > r.y1 - m:
            return False
        for _, a, b, c, d in taken:
            if x0 < c and x1 > a and y0 < d and y1 > b:
                return False
        for o in self.openings:  # eshik oldi 1 m bo'sh, deraza oldi past jihozlar uchun ochiq
            if o.kind == "window":
                continue
            if o.horizontal:
                zone = (o.a - .1, o.c - 1.0, o.b + .1, o.c + 1.0)
            else:
                zone = (o.c - 1.0, o.a - .1, o.c + 1.0, o.b + .1)
            if x0 < zone[2] and x1 > zone[0] and y0 < zone[3] and y1 > zone[1]:
                return False
        return True

    def put(self, r: Room, kind: str, side: str, at: float = .5, gap: float = 0.0, offset: float = 0.0, rotate=False):
        """Mebelni devor bo'yiga qo'yadi: side - qaysi devor, at - devor bo'ylab joyi (0..1)."""
        w, d = FURNITURE[kind][0], FURNITURE[kind][1]
        taken = r.furniture
        for shift in (0, .15, -.15, .3, -.3, .45, -.45):
            p = min(.95, max(.05, at + shift))
            if side in ("bottom", "top"):
                ww, dd = (d, w) if rotate else (w, d)
                cx = r.x0 + p * r.w
                x0 = max(r.x0 + .06, min(cx - ww / 2, r.x1 - .06 - ww))
                y0 = r.y0 + .06 + gap + offset if side == "bottom" else r.y1 - .06 - dd - gap - offset
                box = (x0, y0, x0 + ww, y0 + dd)
            else:
                ww, dd = (w, d) if rotate else (d, w)
                cy = r.y0 + p * r.h
                y0 = max(r.y0 + .06, min(cy - dd / 2, r.y1 - .06 - dd))
                x0 = r.x0 + .06 + gap + offset if side == "left" else r.x1 - .06 - ww - gap - offset
                box = (x0, y0, x0 + ww, y0 + dd)
            if self._free(r, box, taken):
                taken.append((kind, *box))
                return box
        return None

    def furnish(self):
        for r in self.rooms:
            long_sides = ("bottom", "top") if r.w >= r.h else ("left", "right")
            short_sides = ("left", "right") if r.w >= r.h else ("bottom", "top")
            k = r.kind
            if k == "living":
                for s in long_sides:
                    if self.put(r, "sofa", s, .5):
                        other = long_sides[1] if s == long_sides[0] else long_sides[0]
                        self.put(r, "tv", other, .5)
                        self.put(r, "coffee_table", s, .5, gap=1.1)
                        break
                for s in short_sides:
                    if self.put(r, "armchair", s, .35):
                        break
            elif k in ("bedroom", "kids"):
                bed = "bed_double" if k == "bedroom" and min(r.w, r.h) >= 2.6 else "bed_single"
                for s in short_sides + long_sides:
                    if self.put(r, bed, s, .5):
                        self.put(r, "nightstand", s, .18) if bed == "bed_double" else None
                        break
                for s in long_sides + short_sides:
                    if self.put(r, "wardrobe", s, .8):
                        break
                if k == "kids":
                    for s in long_sides + short_sides:
                        if self.put(r, "desk", s, .25):
                            break
            elif k == "kitchen":
                for s in long_sides:
                    if self.put(r, "counter", s, .5):
                        break
                for s in short_sides:
                    if self.put(r, "fridge", s, .85):
                        break
                if r.area >= 9:
                    cx, cy = r.x0 + r.w * .55, r.y0 + r.h * .5
                    box = (cx - .6, cy - .4, cx + .6, cy + .4)
                    if self._free(r, box, r.furniture):
                        r.furniture.append(("dining", *box))
            elif k == "bath":
                for s in long_sides:
                    if self.put(r, "bathtub", s, .5) or self.put(r, "shower", s, .2):
                        break
                for s in short_sides + long_sides:
                    if self.put(r, "sink", s, .5):
                        break
                for s in long_sides + short_sides:
                    if self.put(r, "toilet", s, .8):
                        break
                for s in short_sides + long_sides:
                    if self.put(r, "washer", s, .2):
                        break
            elif k == "wc":
                for s in long_sides + short_sides:
                    if self.put(r, "toilet", s, .6):
                        break
                for s in short_sides + long_sides:
                    if self.put(r, "sink", s, .3):
                        break
            elif k in ("hall", "corridor"):
                for s in long_sides + short_sides:
                    if self.put(r, "shoe_rack", s, .7):
                        break
            elif k == "storage":
                for s in long_sides + short_sides:
                    self.put(r, "storage_rack", s, .5)
            elif k == "office":
                n = max(1, int(r.area // 6))
                for i in range(n):
                    side = ("bottom", "top", "left", "right")[i % 4]
                    self.put(r, "desk", side, (i // 4 + 1) / (n // 4 + 2))
            elif k == "fitting":
                self.put(r, "mirror", long_sides[0], .5)
            elif k == "hall_sales":
                self.furnish_shop(r)
            elif k == "cafe_hall":
                self.furnish_cafe(r)

    def furnish_shop(self, r: Room):
        """Savdo zali: devor javonlari, orolcha gondolalar 1.2 m+ yo'lak, kassa kirish yonida, harakat soat strelkasiga qarshi."""
        clothing = self.shop_kind == "clothing"
        unit = "rack" if clothing else "gondola"
        entrance_side = getattr(self, "entrance_side", "bottom")
        far = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}[entrance_side]
        walls = [s for s in ("bottom", "top", "left", "right") if s != entrance_side]
        for s in walls:  # devor bo'ylab javonlar
            length = r.w if s in ("bottom", "top") else r.h
            n = int((length - 0.4) // 1.05)
            for i in range(n):
                self.put(r, "shelf", s, (i + .5) / n)
        # Kassa: kirishdan chiqishda chap tomonda (mijoz o'ngdan kiradi, aylanib chapdan chiqadi)
        mid = getattr(self, "entrance_mid", r.x0 + r.w / 2)
        if entrance_side in ("bottom", "top"):
            at = (mid - r.x0 - 1.9) / r.w
        else:
            at = (mid - r.y0 - 1.9) / r.h
        self.put(r, "cashier", entrance_side, max(.08, at), gap=1.3)
        # Orolcha gondolalar: dekompressiya zonasi (kirishdan 2 m) va devor javonlaridan 1.3 m yo'lak qoldiriladi
        inner = (r.x0 + .6 + 1.3, r.y0 + .6 + 1.3, r.x1 - .6 - 1.3, r.y1 - .6 - 1.3)
        x0, y0, x1, y1 = inner
        if entrance_side == "bottom":
            y0 = max(y0, r.y0 + 2.4)
        elif entrance_side == "top":
            y1 = min(y1, r.y1 - 2.4)
        elif entrance_side == "left":
            x0 = max(x0, r.x0 + 2.4)
        else:
            x1 = min(x1, r.x1 - 2.4)
        w, d = FURNITURE[unit][0], FURNITURE[unit][1]
        vertical_rows = entrance_side in ("bottom", "top")
        span = (x1 - x0) if vertical_rows else (y1 - y0)
        depth = (y1 - y0) if vertical_rows else (x1 - x0)
        pitch = d + 1.3
        rows = int((span + 1.3) // pitch)
        per = max(1, int(depth // (w + 0.05)))
        for i in range(rows):
            for j in range(per):
                if vertical_rows:
                    bx = x0 + i * pitch
                    by = y0 + j * (w + .05)
                    box = (bx, by, bx + d, by + w)
                else:
                    by = y0 + i * pitch
                    bx = x0 + j * (w + .05)
                    box = (bx, by, bx + w, by + d)
                if self._free(r, box, r.furniture):
                    r.furniture.append((unit, *box))
        # Harakat yo'li (soat strelkasiga qarshi) va zonalar
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        m = 1.1
        loop = [(r.x1 - m, r.y0 + m), (r.x1 - m, r.y1 - m), (r.x0 + m, r.y1 - m), (r.x0 + m, r.y0 + m)]
        k = {"bottom": 0, "right": 1, "top": 2, "left": 3}[entrance_side]
        self.flow = loop[k:] + loop[:k]
        ent = {"bottom": (mid, r.y0 + .4), "top": (mid, r.y1 - .4), "left": (r.x0 + .4, mid), "right": (r.x1 - .4, mid)}[entrance_side]
        self.flow = [ent] + self.flow + [ent]
        t = ROOM_NAMES  # noqa
        inside = {"bottom": (0, 1.4), "top": (0, -1.4), "left": (1.4, 0), "right": (-1.4, 0)}[entrance_side]
        till = next((f for f in r.furniture if f[0] == "cashier"), None)
        impulse = ((till[1] + till[3]) / 2, (till[2] + till[4]) / 2 + (0.9 if entrance_side == "bottom" else -0.9)) if till \
            else (ent[0] - 1.9, ent[1] + 1.9)
        self.zones += [("Dekompressiya zonasi (2 m bo'sh)", ent[0] + inside[0] + (2.2 if vertical_rows else 0), ent[1] + inside[1]),
                       ("Asosiy tovar - orqa devorda", *{"top": (cx, r.y1 - 1.6), "bottom": (cx, r.y0 + 1.6),
                                                         "left": (r.x0 + 1.6, cy), "right": (r.x1 - 1.6, cy)}[far]),
                       ("Impuls tovar - kassa yonida", *impulse)]
        self.notes += ["Yo'laklar kamida 1.2-1.3 m, kirishda 2 m dekompressiya zonasi bo'sh.",
                       "Mijoz o'ngdan kirib soat strelkasiga qarshi aylanadi; kassa chiqishda.",
                       "Oltin polka: ko'z balandligi 1.2-1.6 m - eng ko'p sotiladigan tovar.",
                       "Asosiy (kundalik) tovar orqa devorda - mijozni butun zaldan o'tkazadi."]

    def furnish_cafe(self, r: Room):
        self.put(r, "bar", "top" if r.w >= r.h else "right", .5)
        bar = next((f for f in r.furniture if f[0] == "bar"), None)
        top = (bar[2] - 1.0) if bar and r.w >= r.h else r.y1 - .6
        px, py = 2.0, 1.6  # 4 kishilik stol joy topmasa - 2 kishilik (stullar yonida)
        cols = int((r.w - .6) // px)
        rows = int((top - r.y0 - .2) // py)
        x_start = r.x0 + (r.w - cols * px) / 2 + px / 2
        for i in range(cols):
            for j in range(rows):
                gx, gy = x_start + i * px, r.y0 + .2 + py / 2 + j * py
                table = (gx - .4, gy - .4, gx + .4, gy + .4)
                sides = [(gx - .87, gy - .21, gx - .45, gy + .21), (gx + .45, gy - .21, gx + .87, gy + .21)]
                ends = [(gx - .21, gy + .45, gx + .21, gy + .87), (gx - .21, gy - .87, gx + .21, gy - .45)]
                for chairs in (sides + ends, sides):
                    if all(self._free(r, b, r.furniture) for b in [table] + chairs):
                        r.furniture.append(("table4", *table))
                        r.furniture += [("chair", *c) for c in chairs]
                        break
        self.notes += ["Stollar orasi kamida 1.2 m (xizmat yo'lagi), 4 kishilik stolga ~2 m² zal maydoni.",
                       "Bar kirishdan ko'rinsin; oshxona eshigi zalga yaqin, mijoz yo'liga to'g'ri kelmasin."]

    # -- devor segmentlari (eshik/deraza o'rinlari kesilgan)
    def walls(self):
        """[(horizontal, a, b, c, thickness)] - ochiqliklar kesilgan devor bo'laklari."""
        segs: dict = {}
        for r in self.rooms:
            for horizontal, a, b, c in ((True, r.x0, r.x1, r.y0), (True, r.x0, r.x1, r.y1),
                                        (False, r.y0, r.y1, r.x0), (False, r.y0, r.y1, r.x1)):
                segs.setdefault((horizontal, round(c, 4)), []).append((a, b))
        out = []
        for (horizontal, c), parts in segs.items():
            exterior = (horizontal and (abs(c) < 1e-6 or abs(c - self.L) < 1e-6)) or \
                       (not horizontal and (abs(c) < 1e-6 or abs(c - self.W) < 1e-6))
            points = sorted({p for ab in parts for p in ab})
            pieces = [(points[i], points[i + 1]) for i in range(len(points) - 1)
                      if any(a <= points[i] + 1e-6 and b >= points[i + 1] - 1e-6 for a, b in parts)]
            cuts = sorted((o.a, o.b, o.kind) for o in self.openings if o.horizontal == horizontal and abs(o.c - c) < 1e-6)
            for a, b in pieces:
                cur = a
                for oa, ob, _ in cuts:
                    if ob <= cur or oa >= b:
                        continue
                    if oa > cur:
                        out.append((horizontal, cur, oa, c, WALL_EXT if exterior else WALL_INT))
                    cur = max(cur, ob)
                if cur < b:
                    out.append((horizontal, cur, b, c, WALL_EXT if exterior else WALL_INT))
        # qo'shni bo'laklarni birlashtirish
        out.sort(key=lambda s: (s[0], s[3], s[1]))
        merged = []
        for s in out:
            if merged and merged[-1][0] == s[0] and abs(merged[-1][3] - s[3]) < 1e-6 and abs(merged[-1][2] - s[1]) < 1e-6 \
                    and merged[-1][4] == s[4]:
                merged[-1] = (s[0], merged[-1][1], s[2], s[3], s[4])
            else:
                merged.append(s)
        return merged


def build_plan(title, purpose, area, width, length, rooms_spec, lang, shop_kind, ceiling) -> Plan:
    purpose = purpose if purpose in ("home", "shop", "cafe", "office") else "home"
    if width and length:
        area = width * length
    area = max(12.0, min(float(area or 60), 2000.0))
    if not (width and length):
        ratio = 1.6 if purpose in ("shop", "cafe") else 1.35
        width, length = round(math.sqrt(area * ratio), 2), round(math.sqrt(area / ratio), 2)
    names = ROOM_NAMES.get(lang, ROOM_NAMES["uz"])
    if rooms_spec:
        prog = []
        for spec in rooms_spec[:16]:
            kind = spec.get("type") if spec.get("type") in ROOM_COLORS else "living"
            prog.append((kind, float(spec.get("area_m2") or 0) or area / len(rooms_spec), _clean(spec.get("name"), 30)))
        total = sum(a for _, a, _ in prog)
        prog = [(k, a * area / total, n) for k, a, n in prog]
    else:
        prog = [(k, a, "") for k, a in default_program(purpose, area, shop_kind)]
    rects = _layout(purpose, prog, width, length)
    rooms, counter = [], {}
    for i, (kind, _, name) in enumerate(prog):
        if str(i) not in rects:
            continue
        counter[kind] = counter.get(kind, 0) + 1
        label = name or names.get(kind, kind) + (f" {counter[kind]}" if sum(k == kind for k, _, _ in prog) > 1 else "")
        x0, y0, x1, y1 = rects[str(i)]
        rooms.append(Room(kind, label, round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)))
    if "corridor" in rects:
        x0, y0, x1, y1 = rects["corridor"]
        rooms.append(Room("hall", names["hall"] if purpose == "home" else names["corridor"], x0, y0, x1, y1))
    plan = Plan(title, purpose, width, length, rooms, lang, shop_kind, ceiling)
    plan.place_openings()
    plan.furnish()
    return plan


PUBLIC = {"living", "kitchen", "dining", "cafe_hall", "hall_sales"}
FRONT = {"hall_sales", "cafe_hall"}


def _row(items, x0, x1, y0, y1):
    """Xonalarni bir qatorga maydoniga mos kenglikda teradi (hammasi yo'lak va tashqi devorga tegadi)."""
    total = sum(a for _, a in items) or 1
    widths = [(x1 - x0) * a / total for _, a in items]
    minimum = min(1.6, (x1 - x0) / max(1, len(items)))  # hech bir xona 1.6 m dan tor bo'lmasin
    for i, wd in enumerate(widths):
        if wd < minimum:
            need = minimum - wd
            widths[i] = minimum
            big = max(range(len(widths)), key=lambda j: widths[j])
            widths[big] -= need
    out, x = {}, x0
    for i, (key, a) in enumerate(items):
        w = widths[i]
        nx = x1 if i == len(items) - 1 else x + w
        out[key] = (x, y0, nx, y1)
        x = nx
    return out


def _layout(purpose, prog, width, length):
    """Uy/ofis: o'rtada yo'lak, pastda umumiy xonalar, tepada shaxsiy xonalar va sanuzel.
    Do'kon/kafe: oldinda (ko'cha tomonda) zal to'liq enida, orqada xizmat xonalari qatori."""
    items = [(str(i), a) for i, (k, a, _) in enumerate(prog) if k not in ("hall", "corridor")]
    kinds = {str(i): k for i, (k, _, _) in enumerate(prog)}
    if purpose in ("shop", "cafe") or any(kinds[k] in FRONT for k, _ in items):
        front = [(k, a) for k, a in items if kinds[k] in FRONT] or [max(items, key=lambda kv: kv[1])]
        back = [(k, a) for k, a in items if (k, a) not in front]
        back_area = sum(a for _, a in back)
        depth = min(max(back_area / width, 2.4), length * .4) if back else 0
        rects = _row(front, 0, width, 0, length - depth)
        if back:
            back.sort(key=lambda kv: kinds[kv[0]] in ("wc", "bath"))  # sanuzel chetda
            rects.update(_row(back, 0, width, length - depth, length))
        return rects
    corridor = 1.4 if width * length < 160 else 1.6
    depth = (length - corridor) / 2
    bottom = [(k, a) for k, a in items if kinds[k] in PUBLIC or kinds[k] == "office"]
    top = [(k, a) for k, a in items if (k, a) not in bottom]
    for item in sorted(bottom, key=lambda kv: kv[1]):  # qatorlar maydoni muvozanati
        if sum(a for _, a in bottom) - item[1] > sum(a for _, a in top) + item[1] and len(bottom) > 1:
            bottom.remove(item)
            top.append(item)
    order = {"bedroom": 0, "kids": 1, "office": 2, "storage": 3, "wc": 4, "bath": 5}
    top.sort(key=lambda kv: order.get(kinds[kv[0]], 2))
    bottom.sort(key=lambda kv: kinds[kv[0]] != "living")
    rects = _row(bottom, 0, width, 0, depth) if bottom else {}
    rects.update(_row(top, 0, width, depth + corridor, length) if top else {})
    rects["corridor"] = (0, depth, width, depth + corridor)
    return rects


def _clean(value, limit=200):
    return " ".join(str(value or "").split())[:limit]


# ------------------------------------------------------------------ DXF (AutoCAD)
def write_dxf(plan: Plan, path):
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    layers = {"A-DEVOR": 7, "A-ESHIK": 3, "A-DERAZA": 5, "A-MEBEL": 8, "A-OLCHAM": 1, "A-MATN": 2, "A-XONA": 9,
              "A-HARAKAT": 6}
    for name, color in layers.items():
        doc.layers.add(name, color=color)
    mm = lambda v: v * 1000
    for horizontal, a, b, c, t in plan.walls():
        if horizontal:
            pts = [(mm(a), mm(c - t / 2)), (mm(b), mm(c - t / 2)), (mm(b), mm(c + t / 2)), (mm(a), mm(c + t / 2))]
        else:
            pts = [(mm(c - t / 2), mm(a)), (mm(c + t / 2), mm(a)), (mm(c + t / 2), mm(b)), (mm(c - t / 2), mm(b))]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "A-DEVOR"})
        hatch = msp.add_hatch(color=7, dxfattribs={"layer": "A-DEVOR"})
        hatch.paths.add_polyline_path(pts, is_closed=True)
    for o in plan.openings:
        a, b, c = mm(o.a), mm(o.b), mm(o.c)
        if o.kind == "window":
            for off in (-120, 0, 120):
                if o.horizontal:
                    msp.add_line((a, c + off), (b, c + off), dxfattribs={"layer": "A-DERAZA"})
                else:
                    msp.add_line((c + off, a), (c + off, b), dxfattribs={"layer": "A-DERAZA"})
        else:
            width = b - a
            room = o.room
            inward = 1
            if room is not None:
                inward = 1 if (o.horizontal and room.y0 * 1000 >= c - 1) or (not o.horizontal and room.x0 * 1000 >= c - 1) else -1
            if o.horizontal:
                msp.add_line((a, c), (a, c + inward * width), dxfattribs={"layer": "A-ESHIK"})
                start, end = (0, 90) if inward > 0 else (270, 360)
                msp.add_arc((a, c), width, start, end, dxfattribs={"layer": "A-ESHIK"})
            else:
                msp.add_line((c, a), (c + inward * width, a), dxfattribs={"layer": "A-ESHIK"})
                start, end = (0, 90) if inward > 0 else (90, 180)
                msp.add_arc((c, a), width, start, end, dxfattribs={"layer": "A-ESHIK"})
    for r in plan.rooms:
        cx, cy = mm((r.x0 + r.x1) / 2), mm((r.y0 + r.y1) / 2)
        msp.add_text(r.name, height=180, dxfattribs={"layer": "A-MATN"}).set_placement((cx, cy + 150), align=TextEntityAlignment.MIDDLE_CENTER)
        msp.add_text(f"{r.area:.1f} m²", height=150, dxfattribs={"layer": "A-MATN"}).set_placement((cx, cy - 150), align=TextEntityAlignment.MIDDLE_CENTER)
        for kind, x0, y0, x1, y1 in r.furniture:
            msp.add_lwpolyline([(mm(x0), mm(y0)), (mm(x1), mm(y0)), (mm(x1), mm(y1)), (mm(x0), mm(y1))], close=True,
                               dxfattribs={"layer": "A-MEBEL"})
            label = FURNITURE[kind][4]
            if label and (x1 - x0) * (y1 - y0) > 0.4:
                msp.add_text(label, height=90, dxfattribs={"layer": "A-MEBEL"}).set_placement(
                    (mm((x0 + x1) / 2), mm((y0 + y1) / 2)), align=TextEntityAlignment.MIDDLE_CENTER)
    if plan.flow:
        msp.add_lwpolyline([(mm(x), mm(y)) for x, y in plan.flow], dxfattribs={"layer": "A-HARAKAT", "linetype": "DASHED"})
    W, L = mm(plan.W), mm(plan.L)
    msp.add_linear_dim(base=(0, -900), p1=(0, 0), p2=(W, 0), dxfattribs={"layer": "A-OLCHAM"}).render()
    msp.add_linear_dim(base=(-900, 0), p1=(0, 0), p2=(0, L), angle=90, dxfattribs={"layer": "A-OLCHAM"}).render()
    for r in plan.rooms:  # tashqi xonalar o'lchami
        if r.y1 >= plan.L - 1e-6:
            msp.add_linear_dim(base=(0, L + 700), p1=(mm(r.x0), L), p2=(mm(r.x1), L), dxfattribs={"layer": "A-OLCHAM"}).render()
        if r.x1 >= plan.W - 1e-6:
            msp.add_linear_dim(base=(W + 700, 0), p1=(W, mm(r.y0)), p2=(W, mm(r.y1)), angle=90, dxfattribs={"layer": "A-OLCHAM"}).render()
    msp.add_text(f"{plan.title} | {plan.W * plan.L:.1f} m² | M 1:100", height=300,
                 dxfattribs={"layer": "A-MATN"}).set_placement((0, -2000))
    doc.saveas(path)


# ------------------------------------------------------------------ PNG reja
def _font(size, bold=False):
    from PIL import ImageFont
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
                 ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render_plan_png(plan: Plan, path):
    from PIL import Image, ImageDraw
    scale = min(2000 / plan.W, 1300 / plan.L)
    pad_l, pad_t, pad_b = 170, 170, 260
    Wpx, Hpx = int(plan.W * scale) + pad_l * 2, int(plan.L * scale) + pad_t + pad_b
    img = Image.new("RGB", (Wpx, Hpx), "#FFFFFF")
    d = ImageDraw.Draw(img)
    X = lambda x: pad_l + x * scale
    Y = lambda y: pad_t + (plan.L - y) * scale
    for r in plan.rooms:
        d.rectangle([X(r.x0), Y(r.y1), X(r.x1), Y(r.y0)], fill=ROOM_COLORS.get(r.kind, "#EEE"))
    for r in plan.rooms:
        for kind, x0, y0, x1, y1 in r.furniture:
            color = FURNITURE[kind][3]
            d.rounded_rectangle([X(x0), Y(y1), X(x1), Y(y0)], radius=max(2, int(scale * .05)), fill=color, outline="#3D405B", width=2)
            label = FURNITURE[kind][4]
            if label and (x1 - x0) * scale > 70 and (y1 - y0) * scale > 22:
                f = _font(max(11, int(scale * .16)))
                d.text(((X(x0) + X(x1)) / 2, (Y(y0) + Y(y1)) / 2), label, fill="#1D1D1D", font=f, anchor="mm")
    if plan.flow:
        pts = [(X(x), Y(y)) for x, y in plan.flow]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(bx - ax, by - ay) // 22))
            for i in range(0, n, 2):
                d.line([(ax + (bx - ax) * i / n, ay + (by - ay) * i / n), (ax + (bx - ax) * (i + 1) / n, ay + (by - ay) * (i + 1) / n)],
                       fill="#E63946", width=4)
            ang = math.atan2(by - ay, bx - ax)
            mx, my = (ax + bx) / 2, (ay + by) / 2
            d.polygon([(mx + 16 * math.cos(ang), my + 16 * math.sin(ang)),
                       (mx + 10 * math.cos(ang + 2.5), my + 10 * math.sin(ang + 2.5)),
                       (mx + 10 * math.cos(ang - 2.5), my + 10 * math.sin(ang - 2.5))], fill="#E63946")
    for horizontal, a, b, c, t in plan.walls():
        if horizontal:
            d.rectangle([X(a), Y(c + t / 2), X(b), Y(c - t / 2)], fill="#222222")
        else:
            d.rectangle([X(c - t / 2), Y(b), X(c + t / 2), Y(a)], fill="#222222")
    for o in plan.openings:
        if o.kind == "window":
            if o.horizontal:
                box = [X(o.a), Y(o.c + .19), X(o.b), Y(o.c - .19)]
            else:
                box = [X(o.c - .19), Y(o.b), X(o.c + .19), Y(o.a)]
            d.rectangle(box, fill="#BEE3F8", outline="#1D4E89", width=3)
            if o.horizontal:
                d.line([X(o.a), Y(o.c), X(o.b), Y(o.c)], fill="#1D4E89", width=2)
            else:
                d.line([X(o.c), Y(o.a), X(o.c), Y(o.b)], fill="#1D4E89", width=2)
        else:
            w = (o.b - o.a) * scale
            color = "#2A9D8F" if o.kind == "entrance" else "#555555"
            room = o.room
            if o.horizontal:
                inward = 1 if room is None or room.y0 >= o.c - 1e-6 else -1
                cx, cy = X(o.a), Y(o.c)
                d.line([cx, cy, cx, cy - inward * w], fill=color, width=4)
                box = [cx - w, cy - w, cx + w, cy + w]
                d.arc(box, 270, 360, fill=color, width=2) if inward > 0 else d.arc(box, 0, 90, fill=color, width=2)
            else:
                inward = 1 if room is None or room.x0 >= o.c - 1e-6 else -1
                cx, cy = X(o.c), Y(o.a)
                d.line([cx, cy, cx + inward * w, cy], fill=color, width=4)
                box = [cx - w, cy - w, cx + w, cy + w]
                d.arc(box, 270, 360, fill=color, width=2) if inward > 0 else d.arc(box, 180, 270, fill=color, width=2)
            if o.kind == "entrance":
                f = _font(26, True)
                if o.horizontal:
                    tx, ty = (X(o.a) + X(o.b)) / 2, Y(o.c) + (40 if o.c < 1e-6 else -40)
                else:  # yon devor: yozuv ichkarida, o'lcham chizig'iga tegmaydi
                    tx, ty = X(o.c) + (95 if o.c < 1e-6 else -95), (Y(o.a) + Y(o.b)) / 2 - 34
                d.text((tx, ty), "KIRISH", fill="#2A9D8F", font=f, anchor="mm")
    for r in plan.rooms:
        cx, cy = (X(r.x0) + X(r.x1)) / 2, (Y(r.y0) + Y(r.y1)) / 2
        f1, f2 = _font(max(16, min(34, int(scale * .32))), True), _font(max(14, min(28, int(scale * .26))))
        tw = d.textlength(r.name, font=f1)
        if tw < (r.w * scale - 10):
            d.rounded_rectangle([cx - tw / 2 - 10, cy - 30, cx + tw / 2 + 10, cy + 34], radius=10, fill="#FFFFFFCC")
            d.text((cx, cy - 10), r.name, fill="#1D3557", font=f1, anchor="mm")
            d.text((cx, cy + 18), f"{r.area:.1f} m²", fill="#457B9D", font=f2, anchor="mm")
    for text, x, y in plan.zones:
        f = _font(20, True)
        tw = d.textlength(text, font=f)
        d.rounded_rectangle([X(x) - tw / 2 - 8, Y(y) - 16, X(x) + tw / 2 + 8, Y(y) + 16], radius=8, fill="#E63946")
        d.text((X(x), Y(y)), text, fill="#FFFFFF", font=f, anchor="mm")
    # o'lchamlar
    f = _font(24, True)
    y_dim = Y(0) + 70
    d.line([X(0), y_dim, X(plan.W), y_dim], fill="#C1121F", width=2)
    for xx in (X(0), X(plan.W)):
        d.line([xx, y_dim - 12, xx, y_dim + 12], fill="#C1121F", width=2)
    d.text(((X(0) + X(plan.W)) / 2, y_dim + 24), f"{plan.W:.2f} m", fill="#C1121F", font=f, anchor="mm")
    x_dim = X(0) - 70
    d.line([x_dim, Y(0), x_dim, Y(plan.L)], fill="#C1121F", width=2)
    for yy in (Y(0), Y(plan.L)):
        d.line([x_dim - 12, yy, x_dim + 12, yy], fill="#C1121F", width=2)
    txt = Image.new("RGBA", (260, 40), (0, 0, 0, 0))
    ImageDraw.Draw(txt).text((130, 20), f"{plan.L:.2f} m", fill="#C1121F", font=f, anchor="mm")
    txt = txt.rotate(90, expand=True)
    img.paste(txt, (int(x_dim - 48), int((Y(0) + Y(plan.L)) / 2 - 130)), txt)
    # sarlavha va masshtab
    d.text((pad_l, 60), plan.title, fill="#1D3557", font=_font(44, True))
    d.text((pad_l, 115), f"Umumiy maydon: {plan.W * plan.L:.1f} m²  ·  {len(plan.rooms)} xona  ·  shift {plan.ceiling:.1f} m",
           fill="#457B9D", font=_font(26))
    bar_y = Hpx - 120
    d.rectangle([pad_l, bar_y, pad_l + scale, bar_y + 12], fill="#222")
    d.rectangle([pad_l + scale, bar_y, pad_l + 2 * scale, bar_y + 12], outline="#222", width=2)
    d.text((pad_l, bar_y + 22), "0", fill="#222", font=_font(20))
    d.text((pad_l + 2 * scale, bar_y + 22), "2 m", fill="#222", font=_font(20), anchor="ma")
    if plan.notes:
        d.text((pad_l + 2 * scale + 80, bar_y - 6), "\n".join("• " + n for n in plan.notes[:4]), fill="#333", font=_font(20))
    nx, ny = Wpx - 110, 90
    d.polygon([(nx, ny - 45), (nx - 20, ny + 15), (nx, ny), (nx + 20, ny + 15)], fill="#1D3557")
    d.text((nx, ny + 40), "N", fill="#1D3557", font=_font(28, True), anchor="mm")
    img.save(path, optimize=True)


# ------------------------------------------------------------------ 3D (OBJ + izometrik PNG)
def plan_boxes(plan: Plan, cut: float | None = None):
    """3D qutilar ro'yxati: (x0, y0, z0, x1, y1, z1, rang, material)."""
    H = plan.ceiling
    top = cut or H
    boxes = []
    for r in plan.rooms:
        boxes.append((r.x0, r.y0, 0, r.x1, r.y1, .02, ROOM_COLORS.get(r.kind, "#EEEEEE"), "pol_" + r.kind))
    for horizontal, a, b, c, t in plan.walls():
        if horizontal:
            boxes.append((a, c - t / 2, 0, b, c + t / 2, top, "#F1F1EE", "devor"))
        else:
            boxes.append((c - t / 2, a, 0, c + t / 2, b, top, "#F1F1EE", "devor"))
    for o in plan.openings:
        t = WALL_EXT if (o.horizontal and (o.c < 1e-6 or abs(o.c - plan.L) < 1e-6)) or \
            (not o.horizontal and (o.c < 1e-6 or abs(o.c - plan.W) < 1e-6)) else WALL_INT
        parts = []
        if o.kind == "window":
            parts += [(0, SILL, "#F1F1EE", "devor"), (SILL, WIN_TOP, "#9AD1F5", "oyna"), (WIN_TOP, H, "#F1F1EE", "devor")]
        else:
            parts += [(DOOR_H, H, "#F1F1EE", "devor")]
        for z0, z1, color, mat in parts:
            z1 = min(z1, top)
            if z1 <= z0:
                continue
            th = t if mat != "oyna" else .04
            if o.horizontal:
                boxes.append((o.a, o.c - th / 2, z0, o.b, o.c + th / 2, z1, color, mat))
            else:
                boxes.append((o.c - th / 2, o.a, z0, o.c + th / 2, o.b, z1, color, mat))
    for r in plan.rooms:
        for kind, x0, y0, x1, y1 in r.furniture:
            boxes.append((x0, y0, .02, x1, y1, .02 + FURNITURE[kind][2], FURNITURE[kind][3], "mebel_" + kind))
    return boxes


def write_obj(plan: Plan, obj_path, mtl_path):
    boxes = plan_boxes(plan)
    mats = {}
    for b in boxes:
        mats.setdefault(b[7], b[6])
    with open(mtl_path, "w", encoding="utf-8") as m:
        for name, color in mats.items():
            r, g, bb = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
            m.write(f"newmtl {name}\nKd {r:.3f} {g:.3f} {bb:.3f}\nKa 0.1 0.1 0.1\n" + ("d 0.35\n" if name == "oyna" else "") + "\n")
    lines = [f"# {plan.title} - Ali dizayn studiyasi (metr, Y yuqoriga)", f"mtllib {mtl_path.name}"]
    v = 1
    for i, (x0, y0, z0, x1, y1, z1, _, mat) in enumerate(boxes):
        # OBJ: X o'ng, Y yuqori, Z oldinga (rejadagi y -> -Z)
        corners = [(x, z, -y) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
        lines.append(f"o {mat}_{i}\nusemtl {mat}")
        lines += [f"v {x:.3f} {y:.3f} {z:.3f}" for x, y, z in corners]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        lines += ["f " + " ".join(str(v + k) for k in f) for f in faces]
        v += 8
    obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _shade(color: str, k: float) -> tuple:
    return tuple(max(0, min(255, int(int(color[i:i + 2], 16) * k))) for i in (1, 3, 5))


def render_3d_png(plan: Plan, path, cut: float = 1.5):
    """Izometrik 'qo'g'irchoq uy' ko'rinishi: devorlar 1.5 m da kesilgan, ichi ko'rinadi."""
    from PIL import Image, ImageDraw
    boxes = plan_boxes(plan, cut=cut)
    ang, elev = math.radians(35), math.radians(32)

    def proj(x, y, z):
        u = (x * math.cos(ang) + y * math.sin(ang))
        v = (-x * math.sin(ang) + y * math.cos(ang)) * math.sin(elev) - z * math.cos(elev)
        return u, v
    pts = [proj(x, y, z) for b in boxes for x in (b[0], b[3]) for y in (b[1], b[4]) for z in (b[2], b[5])]
    umin, umax = min(p[0] for p in pts), max(p[0] for p in pts)
    vmin, vmax = min(p[1] for p in pts), max(p[1] for p in pts)
    W, H = 2000, 1300
    s = min((W - 200) / (umax - umin), (H - 260) / (vmax - vmin))
    ox, oy = 100 - umin * s, 200 - vmin * s
    P = lambda x, y, z: (ox + proj(x, y, z)[0] * s, oy + proj(x, y, z)[1] * s)
    img = Image.new("RGB", (W, H), "#EEF2F7")
    d = ImageDraw.Draw(img)
    for i in range(H):  # osmon gradienti
        k = i / H
        d.line([(0, i), (W, i)], fill=(int(232 - 30 * k), int(238 - 24 * k), int(246 - 12 * k)))
    # kameradan uzoqdan yaqinga (rassom algoritmi); kamera -x, +y tomonda emas: chuqurlik = x*sin - y*cos
    def depth(b):
        cx, cy = (b[0] + b[3]) / 2, (b[1] + b[4]) / 2
        return (-cx * math.sin(ang) + cy * math.cos(ang)), b[2]
    # Ekranda pastroq (yaqinroq) = -x*sin + y*cos katta. Avval pollar, keyin uzoqdan yaqinga.
    floors = [b for b in boxes if b[7].startswith("pol_")]
    solids = sorted((b for b in boxes if not b[7].startswith("pol_")), key=lambda b: (depth(b)[0], b[2]))
    for b in floors + solids:
        x0, y0, z0, x1, y1, z1, color, mat = b
        top = [P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)]
        front = [P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, z1), P(x0, y1, z1)]   # +y tomoni (kameraga qaragan)
        side = [P(x0, y0, z0), P(x0, y1, z0), P(x0, y1, z1), P(x0, y0, z1)]    # -x tomoni
        outline = (90, 96, 110) if not mat.startswith("pol_") else None
        d.polygon(side, fill=_shade(color, .72), outline=outline)
        d.polygon(front, fill=_shade(color, .86), outline=outline)
        d.polygon(top, fill=_shade(color, 1.0) if mat != "devor" else (70, 74, 84), outline=outline)
    f = _font(40, True)
    d.text((60, 50), plan.title + " - 3D ko'rinish", fill="#1D3557", font=f)
    d.text((60, 105), f"{plan.W * plan.L:.1f} m² · shift {plan.ceiling:.1f} m · devorlar {cut} m da kesimda ko'rsatilgan",
           fill="#457B9D", font=_font(24))
    img.save(path, optimize=True)


# ------------------------------------------------------------------ vosita
@skill(
    description=(
        "Uy / kvartira / do'kon / kafe / ofis uchun KONSEPT REJA va 3D. Maydon (area_m2) yoki eni va bo'yi (width_m, "
        "length_m) bo'yicha xonalarni joylaydi, eshik-derazalarni qo'yadi, mebel va jihozlarni joylashtiradi "
        "(do'konda: devor javonlari, gondolalar, 1.3 m yo'laklar, kassa, mijoz harakati yo'li va zonalar; kafeda: bar va "
        "stollar). Natija avtomatik yuboriladi: AutoCAD .dxf chizma (mm, qatlamlar, o'lchamlar), reja PNG, 3ds Max/Blender "
        "uchun .obj+.mtl 3D model va 3D ko'rinish PNG. rooms berilsa - [{type, area_m2, name}], type: " + ", ".join(ROOM_COLORS)
        + ". shop_kind: grocery|clothing|pharmacy|electronics."
    ),
    params={
        "title": {"type": "string", "description": "Loyiha nomi, masalan '3 xonali uy 98 m²' yoki 'Oziq-ovqat do'koni'"},
        "purpose": {"type": "string", "enum": ["home", "shop", "cafe", "office"], "description": "Bino vazifasi"},
        "area_m2": {"type": "number", "description": "Umumiy maydon, m²"},
        "width_m": {"type": "number", "description": "Eni, m (bo'yi bilan birga berilsa maydon o'rniga)"},
        "length_m": {"type": "number", "description": "Bo'yi, m"},
        "rooms": {"type": "array", "items": {"type": "object"}, "description": "Xonalar (ixtiyoriy)"},
        "shop_kind": {"type": "string", "description": "Do'kon turi"},
        "ceiling_m": {"type": "number", "description": "Shift balandligi (standart 2.8)"},
        "language": {"type": "string", "enum": ["uz", "ru"], "description": "Xona nomlari tili"},
    },
    required=["title", "purpose"],
)
def design_floor_plan(title: str, purpose: str, area_m2: float = 0, width_m: float = 0, length_m: float = 0,
                      rooms: list | None = None, shop_kind: str = "grocery", ceiling_m: float = 2.8,
                      language: str = "uz") -> str:
    title = _clean(title, 100) or "Reja"
    try:
        plan = build_plan(title, purpose, area_m2, width_m, length_m, [r for r in rooms or [] if isinstance(r, dict)],
                          language if language in ROOM_NAMES else "uz", shop_kind or "grocery",
                          max(2.4, min(float(ceiling_m or 2.8), 6.0)))
    except (ValueError, ZeroDivisionError) as e:
        return f"Reja tuzilmadi: {e}"
    base = outbox.new_path(title, "dxf")
    stem = base.with_suffix("")
    write_dxf(plan, base)
    png = stem.parent / (stem.name + "_reja.png")
    render_plan_png(plan, png)
    obj, mtl = stem.parent / (stem.name + "_3d.obj"), stem.parent / (stem.name + "_3d.mtl")
    write_obj(plan, obj, mtl)
    view = stem.parent / (stem.name + "_3d.png")
    render_3d_png(plan, view)
    for p in (png, view, base, obj, mtl):
        outbox.register(p)
    rooms_text = "; ".join(f"{r.name} {r.area:.1f} m²" for r in plan.rooms)
    items = sum(len(r.furniture) for r in plan.rooms)
    return (f"✅ Reja tayyor: {plan.W:.2f} × {plan.L:.2f} m = {plan.W * plan.L:.1f} m². Xonalar: {rooms_text}. "
            f"{len([o for o in plan.openings if o.kind != 'window'])} eshik, {len([o for o in plan.openings if o.kind == 'window'])} "
            f"deraza, {items} ta mebel/jihoz. Fayllar avtomatik yuboriladi: reja PNG, 3D PNG, AutoCAD .dxf, 3ds Max uchun "
            ".obj+.mtl. " + (" ".join(plan.notes) + " " if plan.notes else "") +
            "Bu konsept: qurilish/ta'mirdan oldin joyida o'lchab, me'mor bilan tekshiring.")
