from __future__ import annotations

import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ── Font resolution ──────────────────────────────────────────────────────────

_FONT_DIRS = [
    "/System/Library/Fonts/Supplemental",
    "/System/Library/Fonts",
    "/Library/Fonts",
    "/usr/share/fonts/truetype/dejavu",        # Linux fallback
    "/usr/share/fonts/truetype/liberation",
]

# role -> ordered list of (filename, ttc_index) candidates
_FONT_CANDIDATES = {
    "serif":        [("Times New Roman.ttf", 0), ("Times.ttc", 0), ("DejaVuSerif.ttf", 0)],
    "serif_bold":   [("Times New Roman Bold.ttf", 0), ("DejaVuSerif-Bold.ttf", 0)],
    "sans":         [("Arial.ttf", 0), ("Helvetica.ttc", 0), ("DejaVuSans.ttf", 0)],
    "sans_bold":    [("Arial Bold.ttf", 0), ("DejaVuSans-Bold.ttf", 0)],
    "mono":         [("Courier New.ttf", 0), ("Courier.ttc", 0), ("DejaVuSansMono.ttf", 0)],
    "mono_bold":    [("Courier New Bold.ttf", 0), ("DejaVuSansMono-Bold.ttf", 0)],
    "hand":         [("Bradley Hand Bold.ttf", 0), ("Noteworthy.ttc", 0),
                     ("Chalkduster.ttf", 0), ("Comic Sans MS.ttf", 0)],
    "hand_alt":     [("Noteworthy.ttc", 0), ("Comic Sans MS.ttf", 0),
                     ("Bradley Hand Bold.ttf", 0)],
    "hi":           [("DevanagariMT.ttc", 0), ("Kohinoor.ttc", 0)],
    "kn":           [("Kannada Sangam MN.ttc", 0), ("NotoSansKannada.ttc", 0)],
    "ta":           [("Tamil Sangam MN.ttc", 0)],
}

_font_path_cache: dict[str, tuple[str, int] | None] = {}


def _resolve_path(role: str) -> tuple[str, int] | None:
    if role in _font_path_cache:
        return _font_path_cache[role]
    for fname, idx in _FONT_CANDIDATES.get(role, []):
        for d in _FONT_DIRS:
            p = os.path.join(d, fname)
            if os.path.exists(p):
                _font_path_cache[role] = (p, idx)
                return _font_path_cache[role]
    _font_path_cache[role] = None
    return None


def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font for a role/size, falling back to Pillow's default."""
    resolved = _resolve_path(role)
    if resolved is None:
        return ImageFont.load_default()
    path, idx = resolved
    try:
        return ImageFont.truetype(path, size=size, index=idx)
    except Exception:
        return ImageFont.load_default()


# ── Canvas: simple top-down text layout ──────────────────────────────────────

class Canvas:
    """A white page you write onto with a moving vertical cursor."""

    def __init__(self, width: int = 1000, height: int = 1400,
                 margin: int = 60, bg: tuple[int, int, int] = (252, 252, 250)):
        self.width = width
        self.height = height
        self.margin = margin
        self.img = Image.new("RGB", (width, height), bg)
        self.draw = ImageDraw.Draw(self.img)
        self.y = margin

    # -- primitives --
    def text(self, s: str, fnt: ImageFont.FreeTypeFont, *, x: int | None = None,
             color=(20, 20, 20), align: str = "left", dy: int | None = None,
             jitter: int = 0) -> None:
        """Write one line at the cursor, advancing y. ``jitter`` randomly nudges
        the baseline (used for a handwritten feel)."""
        if x is None:
            x = self.margin
        ascent, descent = fnt.getmetrics()
        line_h = ascent + descent
        if align in ("center", "right"):
            w = self.draw.textlength(s, font=fnt)
            if align == "center":
                x = (self.width - w) / 2
            else:
                x = self.width - self.margin - w
        yy = self.y + (random.randint(-jitter, jitter) if jitter else 0)
        self.draw.text((x, yy), s, font=fnt, fill=color)
        self.y += dy if dy is not None else line_h + 4

    def kv(self, key: str, value: str, fnt, *, key_color=(70, 70, 70),
           val_color=(20, 20, 20)) -> None:
        """Render a 'Label: value' line with the label greyed out."""
        x = self.margin
        self.draw.text((x, self.y), key, font=fnt, fill=key_color)
        kw = self.draw.textlength(key + " ", font=fnt)
        self.draw.text((x + kw, self.y), value, font=fnt, fill=val_color)
        ascent, descent = fnt.getmetrics()
        self.y += ascent + descent + 4

    def rule(self, *, dashed: bool = False, color=(120, 120, 120), pad: int = 6) -> None:
        self.y += pad
        if dashed:
            x = self.margin
            while x < self.width - self.margin:
                self.draw.line([(x, self.y), (min(x + 8, self.width - self.margin), self.y)],
                               fill=color, width=1)
                x += 14
        else:
            self.draw.line([(self.margin, self.y), (self.width - self.margin, self.y)],
                           fill=color, width=2)
        self.y += pad

    def gap(self, h: int = 12) -> None:
        self.y += h

    def row(self, cells: list[str], xs: list[int], fnt, *, color=(20, 20, 20),
            bold_fnt=None) -> None:
        """A table row: cells positioned at absolute x offsets."""
        for s, x in zip(cells, xs):
            self.draw.text((self.margin + x, self.y), s, font=fnt, fill=color)
        ascent, descent = fnt.getmetrics()
        self.y += ascent + descent + 6

    def finish(self) -> Image.Image:
        """Crop to the used height (plus footer margin)."""
        bottom = min(self.height, self.y + self.margin)
        return self.img.crop((0, 0, self.width, bottom))


# ── Overlays: stamps & signatures ────────────────────────────────────────────

def add_signature(img: Image.Image, name: str, rng: random.Random,
                   anchor: str = "br") -> Image.Image:
    """Draw a squiggly ink signature + printed name near a corner."""
    w, h = img.size
    color = rng.choice([(20, 40, 130), (10, 10, 60), (15, 15, 15)])
    cx = w - 230 if "r" in anchor else 90
    cy = h - 120 if "b" in anchor else 120
    draw = ImageDraw.Draw(img)
    # a flowing stroke made of connected jittered points
    pts = []
    x = cx
    for i in range(rng.randint(18, 28)):
        x += rng.randint(6, 12)
        y = cy + int(22 * math.sin(i * 0.7 + rng.random())) + rng.randint(-6, 6)
        pts.append((x, y))
    draw.line(pts, fill=color, width=rng.randint(2, 3), joint="curve")
    # a couple of loops
    for _ in range(rng.randint(1, 2)):
        lx = rng.randint(cx, cx + 120)
        draw.arc([lx, cy - 18, lx + 26, cy + 14], 0, 300, fill=color, width=2)
    sig_font = font("hand", 26)
    draw.text((cx, cy + 26), name.replace("Dr. ", "Dr "), font=sig_font, fill=color)
    return img


def add_stamp(img: Image.Image, text_lines: list[str], rng: random.Random,
              anchor: str = "br") -> Image.Image:
    """Overlay a semi-transparent rotated circular rubber stamp."""
    color = rng.choice([(180, 30, 30), (30, 60, 170), (130, 30, 110)])
    size = rng.randint(150, 190)
    stamp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(stamp)
    pad = 8
    d.ellipse([pad, pad, size - pad, size - pad], outline=color + (200,), width=3)
    d.ellipse([pad + 12, pad + 12, size - pad - 12, size - pad - 12],
              outline=color + (200,), width=2)
    f = font("sans_bold", 15)
    fy = size // 2 - len(text_lines) * 10
    for line in text_lines:
        tw = d.textlength(line, font=f)
        d.text(((size - tw) / 2, fy), line, font=f, fill=color + (220,))
        fy += 20
    stamp = stamp.rotate(rng.randint(-25, 25), expand=True, resample=Image.BICUBIC)
    w, h = img.size
    sx = w - stamp.width - 60 if "r" in anchor else 60
    sy = h - stamp.height - 40 if "b" in anchor else 60
    base = img.convert("RGBA")
    base.alpha_composite(stamp, (max(0, sx), max(0, sy)))
    return base.convert("RGB")


def add_correction(img: Image.Image, rng: random.Random) -> Image.Image:
    """Simulate a manual pen correction: strike through a random line and
    scribble a value above it."""
    w, h = img.size
    draw = ImageDraw.Draw(img)
    color = (15, 25, 120)
    y = rng.randint(int(h * 0.3), int(h * 0.7))
    x0 = rng.randint(80, w // 2)
    x1 = x0 + rng.randint(120, 220)
    draw.line([(x0, y), (x1, y)], fill=color, width=3)              # strike-through
    draw.text((x0 + 10, y - 34), rng.choice(["corrected", "rev.", "Rs." + str(rng.randint(200, 900))]),
              font=font("hand", 22), fill=color)
    return img


# ── Quality degradations ─────────────────────────────────────────────────────

def fade(img: Image.Image, rng: random.Random) -> Image.Image:
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.45, 0.7))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(1.08, 1.25))
    return Image.blend(img, Image.new("RGB", img.size, (255, 255, 255)),
                       rng.uniform(0.12, 0.28))


def blur(img: Image.Image, rng: random.Random) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(rng.uniform(0.8, 1.8)))


def add_noise(img: Image.Image, rng: random.Random) -> Image.Image:
    arr = np.asarray(img).astype(np.int16)
    sigma = rng.uniform(8, 22)
    noise = np.random.normal(0, sigma, arr.shape)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def skew(img: Image.Image, rng: random.Random) -> Image.Image:
    """Mild perspective + rotation to mimic a phone photo at an angle."""
    img = img.convert("RGB")
    w, h = img.size
    m = 0.06
    dx = lambda: rng.uniform(-m, m) * w
    dy = lambda: rng.uniform(-m, m) * h
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(dx(), dy()), (w + dx(), dy()), (w + dx(), h + dy()), (dx(), h + dy())]
    coeffs = _perspective_coeffs(dst, src)
    img = img.transform((w, h), Image.PERSPECTIVE, coeffs,
                        resample=Image.BICUBIC, fillcolor=(235, 235, 232))
    return img.rotate(rng.uniform(-4, 4), expand=True, resample=Image.BICUBIC,
                      fillcolor=(235, 235, 232))


def _perspective_coeffs(src, dst):
    matrix = []
    for (sx, sy), (dx, dy) in zip(src, dst):
        matrix.append([sx, sy, 1, 0, 0, 0, -dx * sx, -dx * sy])
        matrix.append([0, 0, 0, sx, sy, 1, -dy * sx, -dy * sy])
    A = np.array(matrix, dtype=float)
    B = np.array([c for pt in dst for c in pt], dtype=float)
    res = np.linalg.solve(A, B)
    return res.tolist()


def jpeg_artifacts(img: Image.Image, rng: random.Random) -> Image.Image:
    """Round-trip through low-quality JPEG in memory to add compression noise."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=rng.randint(20, 45))
    buf.seek(0)
    return Image.open(buf).convert("RGB")
