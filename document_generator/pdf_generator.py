from __future__ import annotations

import io
import math
import os
import random
from typing import Optional

from reportlab.lib import colors as rl_colors
from reportlab.pdfgen import canvas as rl_canvas

from . import data
from .data import ClaimContext

# ── Font registration ────────────────────────────────────────────────────────

# Built-in fonts are always available; these may be upgraded on macOS.
_FONTS: dict[str, str] = {
    "sans":       "Helvetica",
    "sans_bold":  "Helvetica-Bold",
    "serif":      "Times-Roman",
    "serif_bold": "Times-Bold",
    "mono":       "Courier",
    "mono_bold":  "Courier-Bold",
    "hand":       "Courier",
    # Regional fonts default to None — PDF will skip the text if unregistered.
    "hi":         None,
    "kn":         None,
    "ta":         None,
}

_FONT_CANDIDATES = {
    "hand": [
        ("/System/Library/Fonts/Supplemental/Comic Sans MS.ttf", "ComicSans"),
    ],
    "hi": [
        ("/System/Library/Fonts/Supplemental/DevanagariMT.ttc", "Devanagari"),
    ],
    "kn": [
        ("/System/Library/Fonts/Supplemental/Kannada Sangam MN.ttc", "KannadaMN"),
    ],
    "ta": [
        ("/System/Library/Fonts/Supplemental/Tamil Sangam MN.ttc", "TamilMN"),
    ],
}


def _register_fonts() -> None:
    for role, candidates in _FONT_CANDIDATES.items():
        for path, name in candidates:
            if not os.path.exists(path):
                continue
            try:
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                pdfmetrics.registerFont(TTFont(name, path))
                _FONTS[role] = name
                break
            except Exception:
                continue


_register_fonts()


def _rf(role: str) -> str:
    """Resolve role → registered font name (Helvetica fallback)."""
    return _FONTS.get(role) or "Helvetica"


def _rgb(t: tuple) -> tuple[float, float, float]:
    """0-255 RGB tuple → 0.0-1.0."""
    return tuple(v / 255 for v in t)  # type: ignore[return-value]


# ── PDFCanvas ────────────────────────────────────────────────────────────────

class PDFCanvas:
    """Thin reportlab wrapper with a top-down cursor (mirrors image Canvas API)."""

    W = 595.27          # A4 width in points
    H = 839         # tall custom page — blank space below content is fine
    MARGIN = 50.0

    def __init__(self):
        self.width  = self.W
        self.height = self.H
        self.margin = self.MARGIN
        self._buf = io.BytesIO()
        self.c = rl_canvas.Canvas(self._buf, pagesize=(self.W, self.H))
        self.y = self.MARGIN   # cursor: distance from TOP

    # -- coordinate helpers --

    def _ry(self, size: float = 0.0) -> float:
        """Convert top-cursor + font size to reportlab baseline y (bottom-up)."""
        return self.H - self.y - size

    # -- primitives --

    def _setfill(self, color) -> None:
        if isinstance(color[0], float) and color[0] <= 1.0:
            self.c.setFillColorRGB(*color)
        else:
            self.c.setFillColorRGB(*_rgb(color))

    def _setstroke(self, color) -> None:
        if isinstance(color[0], float) and color[0] <= 1.0:
            self.c.setStrokeColorRGB(*color)
        else:
            self.c.setStrokeColorRGB(*_rgb(color))

    def text(self, s: str, role: str, size: float, *,
             align: str = "left", color=(0.08, 0.08, 0.08),
             x: Optional[float] = None, dy: Optional[float] = None) -> None:
        fname = _rf(role)
        self.c.setFont(fname, size)
        self._setfill(color)
        tw = self.c.stringWidth(s, fname, size)
        if x is None:
            if align == "center":
                x = (self.W - tw) / 2
            elif align == "right":
                x = self.W - self.margin - tw
            else:
                x = self.margin
        self.c.drawString(x, self._ry(size), s)
        self.y += dy if dy is not None else size + 4

    def kv(self, key: str, value: str, role: str, size: float, *,
           key_color=(0.27, 0.27, 0.27), val_color=(0.08, 0.08, 0.08)) -> None:
        fname = _rf(role)
        self.c.setFont(fname, size)
        ry = self._ry(size)
        self._setfill(key_color)
        self.c.drawString(self.margin, ry, key)
        kw = self.c.stringWidth(key + " ", fname, size)
        self._setfill(val_color)
        self.c.drawString(self.margin + kw, ry, value)
        self.y += size + 4

    def rule(self, *, dashed: bool = False, color=(0.47, 0.47, 0.47), pad: float = 6) -> None:
        self.y += pad
        ry = self.H - self.y
        self._setstroke(color)
        self.c.setLineWidth(1.0 if dashed else 1.5)
        self.c.setDash([6, 5] if dashed else [])
        self.c.line(self.margin, ry, self.W - self.margin, ry)
        self.c.setDash([])
        self.y += pad

    def gap(self, h: float = 12) -> None:
        self.y += h

    def row(self, cells: list, xs: list, role: str, size: float, *,
            color=(0.08, 0.08, 0.08)) -> None:
        fname = _rf(role)
        self.c.setFont(fname, size)
        self._setfill(color)
        ry = self._ry(size)
        for cell, x in zip(cells, xs):
            self.c.drawString(self.margin + x, ry, str(cell))
        self.y += size + 6

    def strikethrough(self, *, x0: Optional[float] = None, x1: Optional[float] = None,
                      color=(0.59, 0.12, 0.12)) -> None:
        """Draw a line through the just-drawn row (call immediately after row())."""
        x0 = x0 or self.margin
        x1 = x1 or (self.W - self.margin)
        ry = self.H - self.y + 10    # midway through the row just drawn
        self._setstroke(color)
        self.c.setLineWidth(1.5)
        self.c.line(x0, ry, x1, ry)

    def finish(self) -> bytes:
        self.c.save()
        return self._buf.getvalue()


# ── PDF variation helpers ─────────────────────────────────────────────────────

def _pdf_stamp(c: rl_canvas.Canvas, text_lines: list[str], rng: random.Random,
               page_h: float, page_w: float, margin: float) -> None:
    """Draw a rotated rubber-stamp ring near the bottom of the page."""
    r_vals = [(0.7, 0.12, 0.12), (0.12, 0.24, 0.67), (0.51, 0.12, 0.43)]
    r, g, b = rng.choice(r_vals)
    radius  = rng.randint(50, 65)
    cx = page_w - margin - radius - rng.randint(0, 30)
    cy = margin + radius + rng.randint(10, 40)
    angle = rng.uniform(-30, 30)

    c.saveState()
    c.translate(cx, cy)
    c.rotate(angle)
    c.setStrokeColorRGB(r, g, b)
    c.setFillColorRGB(r, g, b)
    c.setLineWidth(2)
    c.circle(0, 0, radius, stroke=1, fill=0)
    c.circle(0, 0, radius - 6, stroke=1, fill=0)

    fname = "Helvetica-Bold"
    fsize = 10
    ty = (len(text_lines) - 1) * 6
    for line in text_lines:
        tw = c.stringWidth(line, fname, fsize)
        c.setFont(fname, fsize)
        c.drawString(-tw / 2, ty, line)
        ty -= 13
    c.restoreState()


def _pdf_signature(c: rl_canvas.Canvas, name: str, rng: random.Random,
                   page_h: float, page_w: float, margin: float) -> None:
    """Draw an ink-style signature near the bottom-right."""
    r_vals = [(0.08, 0.16, 0.51), (0.04, 0.04, 0.24), (0.06, 0.06, 0.06)]
    r, g, b = rng.choice(r_vals)
    sx = page_w - margin - 200
    sy = margin + 60

    c.saveState()
    c.setStrokeColorRGB(r, g, b)
    c.setFillColorRGB(r, g, b)
    c.setLineWidth(1.8)

    # Squiggly path using bezier curves.
    path = c.beginPath()
    px, py = sx, sy + 20
    path.moveTo(px, py)
    for i in range(rng.randint(14, 22)):
        px += rng.randint(5, 10)
        dy = int(12 * math.sin(i * 0.75 + rng.random())) + rng.randint(-4, 4)
        path.lineTo(px, py + dy)
    c.drawPath(path, stroke=1, fill=0)

    # Loop flourish.
    lx = sx + rng.randint(10, 90)
    c.arc(lx, sy + 5, lx + 22, sy + 24, 0, 300)

    fname = _rf("hand")
    c.setFont(fname, 15)
    display = name.replace("Dr. ", "Dr ")
    c.drawString(sx, sy, display)
    c.restoreState()


def _pdf_correction(c: rl_canvas.Canvas, rng: random.Random,
                    page_h: float, page_w: float, margin: float) -> None:
    """Simulated pen correction: a strikethrough at a random mid-page y."""
    ry = rng.uniform(page_h * 0.28, page_h * 0.60)
    x0 = rng.uniform(margin, page_w * 0.45)
    x1 = x0 + rng.uniform(100, 180)
    c.saveState()
    c.setStrokeColorRGB(0.06, 0.10, 0.47)
    c.setFillColorRGB(0.06, 0.10, 0.47)
    c.setLineWidth(2)
    c.line(x0, ry, x1, ry)
    fname = _rf("hand")
    c.setFont(fname, 12)
    label = rng.choice(["corrected", "rev.", f"Rs.{rng.randint(200, 900)}"])
    c.drawString(x0 + 8, ry + 10, label)
    c.restoreState()


# PDF variations that can be applied to text PDFs.
_PDF_APPLICABLE = {"handwritten", "multilingual", "stamp", "signature", "correction", "partial"}


def _apply_pdf_variations(cv: PDFCanvas, variations: list[str], rng: random.Random,
                          ctx: ClaimContext, doc_type: str) -> bytes:
    """Apply PDF-compatible post-render variations, then return the PDF bytes.

    Note: ``_generate_one`` in generator.py uses rng.getstate()/setstate() when
    format='both', so this function does NOT need to mirror PNG's exact rng-call
    sequence — it just applies whatever makes sense for a text PDF.
    """
    c = cv.c
    if "signature" in variations:
        name = ctx.doctor_name if doc_type in ("prescription", "diagnostic_report") \
            else "Authorized Signatory"
        _pdf_signature(c, name, rng, cv.H, cv.W, cv.MARGIN)
    if "stamp" in variations:
        lines = {
            "prescription": [ctx.clinic_name.split()[0].upper(), "CLINIC", "SEAL"],
            "medical_bill": ["PAID", ctx.clinic_name.split()[0].upper()],
            "diagnostic_report": ["LAB", "VERIFIED"],
            "pharmacy_bill": ["PHARMACY", "PAID"],
        }[doc_type]
        _pdf_stamp(c, lines, rng, cv.H, cv.W, cv.MARGIN)
    if "correction" in variations:
        _pdf_correction(c, rng, cv.H, cv.W, cv.MARGIN)
    # Quality variations (faded, blurry, skewed, noisy, lowres) are image-only — skip.
    # partial: no visual meaning for text PDFs — skip.
    return cv.finish()


# ── Shared helpers ────────────────────────────────────────────────────────────

def _dosage(rng: random.Random) -> str:
    """Identical to generator._dosage — must consume the same rng calls."""
    pattern = rng.choice(["1-0-1", "1-1-1", "0-0-1", "1-0-0", "1-1-0", "0-1-0"])
    dur     = rng.choice([3, 5, 7, 10, 14, 15, 30])
    when    = rng.choice(["after food", "before food", "at bedtime", "SOS"])
    return f"{pattern}  x {dur} days ({when})"


# ── 1. Prescription (PDF) ─────────────────────────────────────────────────────

def generate_prescription_pdf(ctx: ClaimContext | None = None,
                               variations: list[str] | None = None,
                               rng: random.Random | None = None):
    from .generator import _pick_variations
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "prescription")
    hand = "handwritten" in variations
    body_role = "hand" if hand else "serif"

    cv = PDFCanvas()
    cv.text(ctx.clinic_name, "sans_bold", 26, align="center", color=(25, 55, 110))
    cv.text(f"{ctx.doctor_name}, {ctx.doctor_qualification}", "sans", 14, align="center")
    cv.text(f"Reg. No: {ctx.doctor_reg}", "sans", 11, align="center", color=(80, 80, 80))
    cv.text(ctx.clinic_address, "sans", 10, align="center", color=(80, 80, 80))
    cv.text(f"Phone: {ctx.clinic_phone}", "sans", 10, align="center", color=(80, 80, 80))
    if "multilingual" in variations:
        ctx.language = rng.choice(["hi", "kn", "ta"])
        tagline_font = ctx.language
        tagline = data.MULTILINGUAL_TAGLINES[ctx.language][0]
        if _FONTS.get(tagline_font):
            cv.text(tagline, tagline_font, 13, align="center", color=(120, 60, 60))
    cv.rule()

    cv.text(f"Date: {ctx.consultation_date}", body_role, 13, align="right")
    cv.gap(3)
    cv.kv("Patient Name:", ctx.patient_name, body_role, 13)
    cv.kv("Age / Sex:", f"{ctx.age} yrs / {ctx.sex}", body_role, 13)
    cv.kv("Address:", ctx.patient_address, body_role, 11)
    cv.gap(6)

    cv.text("Chief Complaints:", "sans_bold", 13)
    for comp in ctx.complaints:
        cv.text(f"   - {comp}", body_role, 12)
    cv.gap(5)

    cv.text("Diagnosis:", "sans_bold", 13)
    cv.text(f"   {ctx.diagnosis}", body_role, 14)
    cv.gap(6)

    cv.text("Rx", "serif_bold", 22, color=(25, 55, 110))
    for i, med in enumerate(ctx.medicines, 1):
        kind = "Tab." if "Inhaler" not in med else "Inh."
        cv.text(f"{i}. {kind} {med}", body_role, 14)
        cv.text(f"      {_dosage(rng)}", body_role, 12, color=(60, 60, 60))
    cv.gap(6)

    if ctx.tests:
        cv.text("Investigations Advised:", "sans_bold", 13)
        for t in ctx.tests:
            cv.text(f"   - {t}", body_role, 12)
        cv.gap(4)
    if ctx.procedure:
        cv.kv("Procedure Advised:", ctx.procedure, body_role, 12)

    cv.gap(8)
    cv.kv("Follow-up:", ctx.follow_up_date, body_role, 12)
    cv.gap(35)
    cv.text("Doctor's Signature & Stamp", "sans", 10, align="right", color=(120, 120, 120))

    pdf_bytes = _apply_pdf_variations(cv, variations, rng, ctx, "prescription")
    gt = {
        "doc_type": "prescription",
        "format": "pdf",
        "variations": [v for v in variations if v in _PDF_APPLICABLE],
        "ground_truth": {
            "doctor_name": ctx.doctor_name,
            "doctor_registration": ctx.doctor_reg,
            "patient_name": ctx.patient_name,
            "consultation_date": ctx.consultation_date,
            "diagnosis": ctx.diagnosis,
            "medicines_prescribed": ctx.medicines,
            "tests_advised": ctx.tests,
            "procedures": [ctx.procedure] if ctx.procedure else [],
        },
    }
    return pdf_bytes, gt


# ── 2. Medical bill / invoice (PDF) ──────────────────────────────────────────

# Column x-offsets (relative to margin) for the bill table on A4 (usable ~495pt).
_BILL_XS = [0, 370]   # PARTICULARS, AMOUNT


def generate_medical_bill_pdf(ctx: ClaimContext | None = None,
                              variations: list[str] | None = None,
                              rng: random.Random | None = None,
                              *, edge_cases: bool = True,
                              line_items_override: list[tuple[str, int]] | None = None):
    from .generator import _pick_variations
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "medical_bill")

    cancelled = None
    refund    = None
    is_family = False

    if line_items_override is not None:
        line_items: list[tuple[str, int]] = list(line_items_override)
        subtotal = sum(amt for _, amt in line_items)
    else:
        # ── Identical rng calls to PNG generator ──────────────────────────────
        consultation  = rng.choice([500, 800, 1000, 1200, 1500, 2000])
        test_items    = [(t, rng.choice([300, 450, 500, 650, 800, 1200])) for t in ctx.tests]
        proc_items    = [(ctx.procedure, rng.choice([1500, 3000, 5000, 8000]))] if ctx.procedure else []
        medicine_charge = rng.choice([0, 250, 450, 700, 1100])

        if edge_cases:
            if rng.random() < 0.12 and test_items:
                cancelled = test_items.pop()
            if rng.random() < 0.08:
                refund = ("Refund - duplicate charge", -rng.choice([200, 500]))
            if rng.random() < 0.1:
                is_family = True
                ctx.family_members = [ctx.patient_name, rng.choice(data.PATIENT_NAMES)]

        line_items = [("Consultation Fee", consultation)]
        line_items += [(f"  {t}", amt) for t, amt in test_items]
        line_items += [(f"  {p}", amt) for p, amt in proc_items]
        if medicine_charge:
            line_items.append(("Medicines", medicine_charge))
        if refund:
            line_items.append(refund)
        subtotal = sum(amt for _, amt in line_items)
        # ─────────────────────────────────────────────────────────────────────

    total     = subtotal
    bill_no   = data.bill_number(rng, "BILL")
    pay_mode  = rng.choice(data.PAYMENT_MODES)

    cv = PDFCanvas()
    cv.text(ctx.clinic_name, "serif_bold", 24, align="center", color=(30, 30, 30))
    cv.text(ctx.clinic_address, "sans", 10, align="center", color=(80, 80, 80))
    cv.text(f"GST No: {data.gst_number(rng)}", "sans", 10, align="center", color=(80, 80, 80))
    if "multilingual" in variations:
        ctx.language = rng.choice(["hi", "kn", "ta"])
        if _FONTS.get(ctx.language):
            cv.text(data.MULTILINGUAL_TAGLINES[ctx.language][0], ctx.language, 13,
                    align="center", color=(120, 60, 60))
    cv.rule()

    cv.row([f"Bill No: {bill_no}", f"Date: {ctx.consultation_date}"], [0, 320], "sans", 12)
    cv.gap(4)
    cv.text("Patient Details:", "sans_bold", 12)
    if is_family:
        cv.kv("Names:", ", ".join(ctx.family_members), "sans", 12)
    else:
        cv.kv("Name:", ctx.patient_name, "sans", 12)
    cv.kv("Ref. By:", ctx.doctor_name, "sans", 12)
    cv.rule(dashed=True)

    cv.row(["PARTICULARS", "AMOUNT (Rs.)"], _BILL_XS, "sans_bold", 13)
    cv.rule(dashed=True)
    for label, amt in line_items:
        clr = (0.63, 0.16, 0.16) if amt < 0 else (0.08, 0.08, 0.08)
        cv.row([label, f"{amt:,}"], _BILL_XS, "mono", 11, color=clr)
    if cancelled:
        cv.row([f"  {cancelled[0]} (CANCELLED)", f"{cancelled[1]:,}"],
               _BILL_XS, "mono", 11, color=(0.59, 0.59, 0.59))
        cv.strikethrough(color=(0.59, 0.12, 0.12))
    cv.rule(dashed=True)
    cv.row(["TOTAL", f"{total:,}"], _BILL_XS, "mono_bold", 14, color=(25, 55, 110))
    cv.gap(3)
    cv.text(f"Amount in Words: {data.amount_in_words(total)}", "sans", 9, color=(70, 70, 70))
    cv.gap(8)

    if edge_cases and rng.random() < 0.12:
        paid = round(total * rng.uniform(0.4, 0.7))
        cv.kv("Payment Mode:", f"{pay_mode} (PART PAYMENT)", "sans", 12)
        cv.kv("Amount Paid:",  f"Rs.{paid:,}", "sans", 12)
        cv.kv("Balance Due:",  f"Rs.{total - paid:,}", "sans", 12,
              val_color=(0.63, 0.16, 0.16))
    else:
        cv.kv("Payment Mode:", pay_mode, "sans", 12)
        if pay_mode != "Cash":
            cv.kv("Transaction ID:", f"TXN{rng.randint(10**9, 10**10 - 1)}", "sans", 12)
    cv.gap(35)
    cv.text("Authorized Signatory & Stamp", "sans", 10, align="right", color=(120, 120, 120))

    pdf_bytes = _apply_pdf_variations(cv, variations, rng, ctx, "medical_bill")
    if line_items_override is not None:
        consult_fee = float(next((a for l, a in line_items if "Consultation" in l), 0))
        proc_charges = 0.0
        other_charges = float(sum(a for l, a in line_items if "Consultation" not in l and a > 0))
    else:
        consult_fee = float(consultation)
        proc_charges = float(sum(a for _, a in proc_items))
        other_charges = float(sum(a for _, a in test_items) + medicine_charge)
    gt = {
        "doc_type": "medical_bill",
        "format": "pdf",
        "variations": [v for v in variations if v in _PDF_APPLICABLE],
        "ground_truth": {
            "hospital_name": ctx.clinic_name,
            "bill_number": bill_no,
            "bill_date": ctx.consultation_date,
            "patient_name": ctx.patient_name,
            "consultation_fee": consult_fee,
            "procedure_charges": proc_charges,
            "other_charges": other_charges,
            "total_amount": float(total),
            "line_items": [f"{lbl.strip()}: Rs.{amt}" for lbl, amt in line_items],
            "payment_mode": pay_mode,
        },
        "extras": {
            "cancelled_item": cancelled[0] if cancelled else None,
            "refund": refund[1] if refund else None,
            "family_members": ctx.family_members or None,
        },
    }
    return pdf_bytes, gt


# ── 3. Diagnostic test report (PDF) ──────────────────────────────────────────

# Column x-offsets for the report table (usable ~495pt on A4).
_RPT_XS = [0, 200, 285, 365]   # TEST NAME, RESULT, UNIT, NORMAL RANGE


def generate_diagnostic_report_pdf(ctx: ClaimContext | None = None,
                                   variations: list[str] | None = None,
                                   rng: random.Random | None = None):
    from .generator import _pick_variations
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "diagnostic_report")

    # ── Identical rng calls to PNG generator ──────────────────────────────────
    paneled = [t for t in ctx.tests if data.TEST_PANELS.get(t)]
    if not paneled:
        paneled = ["Complete Blood Count (CBC)"]
    lab_name    = rng.choice(data.LAB_NAMES)
    pathologist = "Dr. " + rng.choice(["Nanda", "Krishnan", "Verghese", "Saxena", "Bose"])
    report_id   = f"RPT{rng.randint(100000, 999999)}"
    # ─────────────────────────────────────────────────────────────────────────

    cv = PDFCanvas()
    cv.text(lab_name, "sans_bold", 24, align="center", color=(20, 90, 80))
    acc = data.accreditation(rng)
    cv.text(acc, "sans", 11, align="center", color=(80, 80, 80))
    cv.text(ctx.clinic_address, "sans", 10, align="center", color=(110, 110, 110))
    cv.rule()

    cv.row([f"Patient: {ctx.patient_name}", f"Report ID: {report_id}"], [0, 310], "sans", 11)
    cv.row([f"Age/Sex: {ctx.age}/{ctx.sex[0]}", f"Date: {ctx.consultation_date}"], [0, 310], "sans", 11)
    cv.kv("Ref. By:", ctx.doctor_name, "sans", 11)
    cv.rule(dashed=True)

    cv.row(["TEST NAME", "RESULT", "UNIT", "NORMAL RANGE"], _RPT_XS, "mono_bold", 11)
    cv.rule(dashed=True)

    tests_performed: list[str] = []
    abnormal: list[str] = []

    for panel in paneled:
        rows = data.TEST_PANELS.get(panel) or []
        tests_performed.append(panel)
        cv.text(panel.upper(), "mono_bold", 11, color=(20, 90, 80))
        if not rows:
            cv.text("   See attached imaging / qualitative report.", "mono", 10,
                    color=(90, 90, 90))
            continue
        for name, unit, (lo, hi) in rows:
            # ── Identical rng calls to PNG generator ──────────────────────
            make_abnormal = rng.random() < 0.28
            if isinstance(lo, float) or isinstance(hi, float):
                val = (round(rng.uniform(hi, hi * 1.4), 1) if make_abnormal
                       else round(rng.uniform(lo, hi), 1))
            else:
                val = (rng.randint(int(hi), int(hi * 1.4)) if make_abnormal
                       else rng.randint(int(lo), int(hi)))
            # ────────────────────────────────────────────────────────────────
            flag = ""
            if val > hi:
                flag, clr = " H", (0.67, 0.16, 0.16)
            elif val < lo:
                flag, clr = " L", (0.67, 0.16, 0.16)
            else:
                clr = (0.08, 0.08, 0.08)
            rng_str = f"{lo} - {hi}"
            cv.row([f"  {name}", f"{val}{flag}", unit, rng_str],
                   _RPT_XS, "mono", 11, color=clr)
            if flag.strip():
                abnormal.append(f"{name}: {val} {unit} ({flag.strip()}, ref {rng_str})")
        cv.gap(5)

    cv.rule(dashed=True)
    remark = ("All parameters within normal limits." if not abnormal
              else "Abnormal values flagged (H/L). Clinical correlation advised.")
    cv.kv("Remarks:", remark, "sans", 11)
    cv.gap(25)
    cv.kv("Pathologist:", pathologist, "sans", 11)
    cv.text("(Digitally Signed)", "sans", 10, align="right", color=(120, 120, 120))

    pdf_bytes = _apply_pdf_variations(cv, variations, rng, ctx, "diagnostic_report")
    gt = {
        "doc_type": "diagnostic_report",
        "format": "pdf",
        "variations": [v for v in variations if v in _PDF_APPLICABLE],
        "ground_truth": {
            "lab_name": lab_name,
            "accreditation": acc,
            "report_date": ctx.consultation_date,
            "patient_name": ctx.patient_name,
            "tests_performed": tests_performed,
            "abnormal_findings": abnormal,
            "pathologist": pathologist,
        },
        "extras": {"report_id": report_id},
    }
    return pdf_bytes, gt


# ── 4. Pharmacy bill (PDF) ────────────────────────────────────────────────────

# Column x-offsets for the pharmacy table on A4.
_PH_XS = [0, 28, 195, 255, 305, 350, 400]   # S.No,Medicine,Batch,Exp,Qty,MRP,Amount


def generate_pharmacy_bill_pdf(ctx: ClaimContext | None = None,
                               variations: list[str] | None = None,
                               rng: random.Random | None = None):
    from .generator import _pick_variations
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "pharmacy_bill")

    # ── Identical rng calls to PNG generator ──────────────────────────────────
    pharmacy = rng.choice(data.PHARMACY_NAMES)
    bill_no  = data.bill_number(rng, "PH")
    dl       = data.drug_license(rng)

    rows: list[tuple] = []
    purchased: list[str] = []
    for i, med in enumerate(ctx.medicines, 1):
        mrp   = data.MEDICINE_PRICES.get(med, rng.randint(3, 40))
        qty   = rng.choice([5, 10, 14, 15, 20, 30])
        amt   = mrp * qty
        batch = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2)) + str(rng.randint(100, 999))
        exp   = f"{rng.randint(1, 12):02d}/{rng.randint(25, 28)}"
        rows.append((str(i), med, batch, exp, str(qty), str(mrp), str(amt)))
        purchased.append(f"{med} x{qty} - Rs.{amt}")

    net = sum(int(r[6]) for r in rows)
    # ─────────────────────────────────────────────────────────────────────────

    cv = PDFCanvas()
    cv.text(pharmacy, "sans_bold", 24, align="center", color=(30, 90, 30))
    cv.text(f"Drug License No: {dl}", "sans", 10, align="center", color=(80, 80, 80))
    cv.text(f"GST No: {data.gst_number(rng)}", "sans", 10, align="center", color=(80, 80, 80))
    cv.text(ctx.clinic_address, "sans", 9, align="center", color=(110, 110, 110))
    cv.rule()

    cv.row([f"Bill No: {bill_no}", f"Date: {ctx.consultation_date}"], [0, 310], "sans", 11)
    cv.kv("Patient:", ctx.patient_name, "sans", 11)
    cv.kv("Doctor:",  ctx.doctor_name,  "sans", 11)
    cv.rule(dashed=True)

    cv.row(["S.No", "Medicine", "Batch", "Exp", "Qty", "MRP", "Amount"],
           _PH_XS, "mono_bold", 10)
    cv.rule(dashed=True)
    for r in rows:
        cv.row(list(r), _PH_XS, "mono", 10)
    cv.rule(dashed=True)
    cv.row(["", "", "", "", "", "TOTAL", str(net)], _PH_XS, "mono_bold", 13,
           color=(25, 55, 110))
    cv.gap(35)
    cv.text("Pharmacist Signature & Stamp", "sans", 10, align="right", color=(120, 120, 120))

    pdf_bytes = _apply_pdf_variations(cv, variations, rng, ctx, "pharmacy_bill")
    gt = {
        "doc_type": "pharmacy_bill",
        "format": "pdf",
        "variations": [v for v in variations if v in _PDF_APPLICABLE],
        "ground_truth": {
            "pharmacy_name": pharmacy,
            "drug_license": dl,
            "bill_date": ctx.consultation_date,
            "patient_name": ctx.patient_name,
            "doctor_name": ctx.doctor_name,
            "medicines_purchased": purchased,
            "total_amount": float(net),
        },
    }
    return pdf_bytes, gt


# ── Generator dispatch table (mirrors _GENERATORS in generator.py) ────────────

_PDF_GENERATORS = {
    "prescription":      generate_prescription_pdf,
    "medical_bill":      generate_medical_bill_pdf,
    "diagnostic_report": generate_diagnostic_report_pdf,
    "pharmacy_bill":     generate_pharmacy_bill_pdf,
}
