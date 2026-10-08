"""How a card photo sits in the card's hexagon (shared by focal_sample.py and
export_photo_framing.py). The hexagon is pointy-top, 188 x 214 inside its
border (the app's HexPhoto at 200x226, border 6). A framing is
  scale  the photo's size relative to COVER (1.0 fills the hexagon, 0.8 = 20% smaller)
  ox,oy  the photo's top-left corner relative to the hexagon's centre, in hexagon units
Judged by the subject's OUTLINE (a G x G grid of where the subject is), never
by its bounding box: a box's corners are empty air."""
import numpy as np

HW, HH = 188.0, 214.0
KEEP = 0.97           # "in frame" = at least this much of the subject itself is inside the hexagon
INSET = 0.96          # ...measured against a hexagon 4% smaller, so nothing sits on the border
MAX_SHRINK = 0.70     # as far as it takes (user, 2026-10-08, of an Atlantic Salmon still cut at the 50% limit: a
                      # 2.9:1 photo the fish fills needs ~35%); a small whole subject beats a cropped middle
G = 48

def grid_points(grid):
    g = np.array([c == "1" for c in grid]).reshape(G, G)
    ys, xs = np.nonzero(g)
    return np.stack([(xs + 0.5) / G, (ys + 0.5) / G], axis=1), float(np.mean(g))

def kept(pts, w, h, rel, ox, oy):
    """share of the subject's points that land inside the (inset) hexagon"""
    s = max(HW / w, HH / h) * rel
    x = np.abs(ox + pts[:, 0] * w * s); y = np.abs(oy + pts[:, 1] * h * s)
    hw, hh = HW * INSET, HH * INSET
    return float(np.mean((x <= hw / 2) & (y <= hh / 2 - x * hh / (2 * hw))))

def offsets(w, h, rel):
    """every way the photo can sit: it keeps covering the hexagon where it is
    big enough to, and is centred in a dimension where it is not"""
    cover = max(HW / w, HH / h); dw, dh = w * cover * rel, h * cover * rel
    xs = [-(dw / 2)] if dw <= HW else list(np.linspace(-(dw - HW / 2), -HW / 2, 21))
    ys = [-(dh / 2)] if dh <= HH else list(np.linspace(-(dh - HH / 2), -HH / 2, 21))
    return [(ox, oy) for ox in xs for oy in ys], dw, dh

def best_at(pts, w, h, rel):
    offs, dw, dh = offsets(w, h, rel)
    # most of the subject kept; among equals, the one nearest today's centre crop
    return max(((kept(pts, w, h, rel, ox, oy), -(abs(ox + dw / 2) + abs(oy + dh / 2)), ox, oy) for ox, oy in offs))

def classify(w, h, grid):
    """-> dict(kind, today, kept, scale, ox, oy, fills) or None when nothing was found"""
    pts, fills = grid_points(grid)
    if len(pts) == 0: return None
    cover = max(HW / w, HH / h)
    cox, coy = -w * cover / 2, -h * cover / 2
    today = kept(pts, w, h, 1.0, cox, coy)
    k1, _, ox1, oy1 = best_at(pts, w, h, 1.0)
    if today >= KEEP: kind, rel, ox, oy, k = "ok", 1.0, cox, coy, today
    elif k1 >= KEEP: kind, rel, ox, oy, k = "slide", 1.0, ox1, oy1, k1
    else:
        kind, rel, ox, oy, k = "far", 1.0, ox1, oy1, k1          # if nothing works: the best slide
        for step in range(1, int(MAX_SHRINK * 100) + 1):
            r = 1.0 - step / 100
            kk, _, oxx, oyy = best_at(pts, w, h, r)
            if kk >= KEEP: kind, rel, ox, oy, k = "zoom", r, oxx, oyy, kk; break
    return {"kind": kind, "today": round(today, 3), "kept": round(k, 3), "scale": rel, "ox": ox, "oy": oy, "fills": round(fills, 3)}
