"""Document generators for the four OPD document types, the variation engine,
and batch / claim-set helpers."""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image

from . import data
from .data import ClaimContext
from .rendering import (
    Canvas, add_correction, add_noise, add_signature, add_stamp, blur, fade,
    font, jpeg_artifacts, skew,
)

# Variations applied during rendering vs. as post-processing on the finished image.
RENDER_VARIATIONS = {"handwritten", "multilingual"}
POST_VARIATIONS = {
    "faded", "blurry", "skewed", "noisy", "lowres",
    "stamp", "signature", "correction", "partial",
}
ALL_VARIATIONS = sorted(RENDER_VARIATIONS | POST_VARIATIONS)


# ── Variation orchestration ──────────────────────────────────────────────────

def _pick_variations(rng: random.Random, doc_type: str) -> list[str]:
    """Randomly choose a plausible, non-conflicting set of variations."""
    chosen: list[str] = []
    # Stamps/signatures are common on every doc.
    if rng.random() < 0.8:
        chosen.append("signature")
    if rng.random() < 0.6:
        chosen.append("stamp")
    # Handwriting mostly on prescriptions.
    if doc_type == "prescription" and rng.random() < 0.4:
        chosen.append("handwritten")
    if rng.random() < 0.2:
        chosen.append("multilingual")
    if rng.random() < 0.25:
        chosen.append("correction")
    # Quality issues — at most one capture problem so docs stay legible-ish.
    quality = rng.choices(
        [None, "faded", "blurry", "skewed", "noisy", "lowres"],
        weights=[45, 12, 10, 12, 8, 13],
    )[0]
    if quality:
        chosen.append(quality)
    if rng.random() < 0.08:
        chosen.append("partial")
    return chosen


def _apply_post(img: Image.Image, variations: list[str], rng: random.Random,
                ctx: ClaimContext, doc_type: str) -> Image.Image:
    """Apply post-render variations in a sensible order."""
    if "signature" in variations:
        name = ctx.doctor_name if doc_type in ("prescription", "diagnostic_report") \
            else "Authorized Signatory"
        img = add_signature(img, name, rng)
    if "stamp" in variations:
        lines = {
            "prescription": [ctx.clinic_name.split()[0].upper(), "CLINIC", "SEAL"],
            "medical_bill": ["PAID", ctx.clinic_name.split()[0].upper()],
            "diagnostic_report": ["LAB", "VERIFIED"],
            "pharmacy_bill": ["PHARMACY", "PAID"],
        }[doc_type]
        img = add_stamp(img, lines, rng, anchor=rng.choice(["br", "bl"]))
    if "correction" in variations:
        img = add_correction(img, rng)
    if "faded" in variations:
        img = fade(img, rng)
    if "noisy" in variations:
        img = add_noise(img, rng)
    if "skewed" in variations:
        img = skew(img, rng)
    if "blurry" in variations:
        img = blur(img, rng)
    if "lowres" in variations:
        img = jpeg_artifacts(img, rng)
    if "partial" in variations:
        w, h = img.size
        img = img.crop((0, 0, w, int(h * rng.uniform(0.55, 0.75))))
    return img


def _dosage(rng: random.Random) -> str:
    pattern = rng.choice(["1-0-1", "1-1-1", "0-0-1", "1-0-0", "1-1-0", "0-1-0"])
    dur = rng.choice([3, 5, 7, 10, 14, 15, 30])
    when = rng.choice(["after food", "before food", "at bedtime", "SOS"])
    return f"{pattern}  x {dur} days ({when})"


# ── 1. Prescription ──────────────────────────────────────────────────────────

def generate_prescription(ctx: ClaimContext | None = None,
                          variations: list[str] | None = None,
                          rng: random.Random | None = None):
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "prescription")
    hand = "handwritten" in variations
    body_role = "hand" if hand else "serif"
    jit = 3 if hand else 0

    c = Canvas()
    # Letterhead (always printed).
    c.text(ctx.clinic_name, font("sans_bold", 34), align="center", color=(25, 55, 110))
    c.text(f"{ctx.doctor_name}, {ctx.doctor_qualification}", font("sans", 20), align="center")
    c.text(f"Reg. No: {ctx.doctor_reg}", font("sans", 16), align="center", color=(80, 80, 80))
    c.text(ctx.clinic_address, font("sans", 15), align="center", color=(80, 80, 80))
    c.text(f"Phone: {ctx.clinic_phone}", font("sans", 15), align="center", color=(80, 80, 80))
    if "multilingual" in variations:
        ctx.language = rng.choice(["hi", "kn", "ta"])
        tagline = data.MULTILINGUAL_TAGLINES[ctx.language][0]
        c.text(tagline, font(ctx.language, 20), align="center", color=(120, 60, 60))
    c.rule()

    bfs = font(body_role, 22)
    bf = font(body_role, 20)
    c.text(f"Date: {ctx.consultation_date}", bf, align="right")
    c.gap(4)
    c.kv("Patient Name:", ctx.patient_name, bf)
    c.kv("Age / Sex:", f"{ctx.age} yrs / {ctx.sex}", bf)
    c.kv("Address:", ctx.patient_address, font(body_role, 17))
    c.gap(8)

    c.text("Chief Complaints:", font("sans_bold", 19))
    for comp in ctx.complaints:
        c.text(f"   • {comp}", bf, jitter=jit)
    c.gap(6)

    c.text("Diagnosis:", font("sans_bold", 19))
    c.text(f"   {ctx.diagnosis}", bfs, jitter=jit, color=(20, 20, 20))
    c.gap(8)

    c.text("Rx", font("serif_bold", 30), color=(25, 55, 110))
    for i, med in enumerate(ctx.medicines, 1):
        kind = "Tab." if "Inhaler" not in med else "Inh."
        c.text(f"{i}. {kind} {med}", bfs, jitter=jit)
        c.text(f"      {_dosage(rng)}", bf, color=(60, 60, 60), jitter=jit)
    c.gap(8)

    if ctx.tests:
        c.text("Investigations Advised:", font("sans_bold", 19))
        for t in ctx.tests:
            c.text(f"   • {t}", bf, jitter=jit)
        c.gap(6)
    if ctx.procedure:
        c.kv("Procedure Advised:", ctx.procedure, bf)

    c.gap(10)
    c.kv("Follow-up:", ctx.follow_up_date, bf)
    c.gap(40)
    c.text("Doctor's Signature & Stamp", font("sans", 15), align="right", color=(120, 120, 120))

    img = _apply_post(c.finish(), variations, rng, ctx, "prescription")
    gt = {
        "doc_type": "prescription",
        "variations": variations,
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
    return img, gt


# ── 2. Medical bill / invoice ────────────────────────────────────────────────

def generate_medical_bill(ctx: ClaimContext | None = None,
                          variations: list[str] | None = None,
                          rng: random.Random | None = None,
                          *, edge_cases: bool = True):
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "medical_bill")

    consultation = rng.choice([500, 800, 1000, 1200, 1500, 2000])
    test_items = [(t, rng.choice([300, 450, 500, 650, 800, 1200])) for t in ctx.tests]
    proc_items = [(ctx.procedure, rng.choice([1500, 3000, 5000, 8000]))] if ctx.procedure else []
    medicine_charge = rng.choice([0, 250, 450, 700, 1100])

    # Optional edge cases the guide asks for.
    cancelled = None
    refund = None
    is_family = False
    if edge_cases:
        if rng.random() < 0.12 and test_items:
            cancelled = test_items.pop()                      # cancelled item
        if rng.random() < 0.08:
            refund = ("Refund - duplicate charge", -rng.choice([200, 500]))
        if rng.random() < 0.1:
            is_family = True
            ctx.family_members = [ctx.patient_name, rng.choice(data.PATIENT_NAMES)]

    line_items: list[tuple[str, int]] = [("Consultation Fee", consultation)]
    line_items += [(f"  {t}", amt) for t, amt in test_items]
    line_items += [(f"  {p}", amt) for p, amt in proc_items]
    if medicine_charge:
        line_items.append(("Medicines", medicine_charge))
    if refund:
        line_items.append(refund)

    subtotal = sum(amt for _, amt in line_items)
    gst = round(subtotal * 0.18)
    total = subtotal + gst
    bill_no = data.bill_number(rng, "BILL")
    pay_mode = rng.choice(data.PAYMENT_MODES)

    c = Canvas()
    c.text(ctx.clinic_name, font("serif_bold", 32), align="center", color=(30, 30, 30))
    c.text(ctx.clinic_address, font("sans", 15), align="center", color=(80, 80, 80))
    c.text(f"GST No: {data.gst_number(rng)}", font("sans", 15), align="center", color=(80, 80, 80))
    if "multilingual" in variations:
        ctx.language = rng.choice(["hi", "kn", "ta"])
        c.text(data.MULTILINGUAL_TAGLINES[ctx.language][0], font(ctx.language, 18),
               align="center", color=(120, 60, 60))
    c.rule()

    f = font("sans", 18)
    c.row([f"Bill No: {bill_no}", f"Date: {ctx.consultation_date}"], [0, 560], f)
    c.gap(6)
    c.text("Patient Details:", font("sans_bold", 18))
    if is_family:
        c.kv("Names:", ", ".join(ctx.family_members), f)
    else:
        c.kv("Name:", ctx.patient_name, f)
    c.kv("Ref. By:", ctx.doctor_name, f)
    c.rule(dashed=True)

    c.row(["PARTICULARS", "AMOUNT (Rs.)"], [0, 640], font("sans_bold", 18))
    c.rule(dashed=True)
    mono = font("mono", 18)
    for label, amt in line_items:
        c.row([label, f"{amt:,}"], [0, 640], mono,
              color=(160, 40, 40) if amt < 0 else (20, 20, 20))
    if cancelled:
        # struck-through cancelled item
        c.row([f"  {cancelled[0]} (CANCELLED)", f"{cancelled[1]:,}"], [0, 640],
              mono, color=(150, 150, 150))
        yline = c.y - 18
        c.draw.line([(c.margin, yline), (c.margin + 760, yline)], fill=(150, 30, 30), width=2)
    c.rule(dashed=True)
    c.row(["Sub Total", f"{subtotal:,}"], [0, 640], font("mono_bold", 18))
    c.row(["GST (18%)", f"{gst:,}"], [0, 640], mono)
    c.row(["TOTAL", f"{total:,}"], [0, 640], font("mono_bold", 20), color=(25, 55, 110))
    c.gap(4)
    c.text(f"Amount in Words: {data.amount_in_words(total)}", font("sans", 15),
           color=(70, 70, 70))
    c.gap(10)

    if edge_cases and rng.random() < 0.12:
        paid = round(total * rng.uniform(0.4, 0.7))
        c.kv("Payment Mode:", f"{pay_mode} (PART PAYMENT)", f)
        c.kv("Amount Paid:", f"Rs.{paid:,}", f)
        c.kv("Balance Due:", f"Rs.{total - paid:,}", f, val_color=(160, 40, 40))
    else:
        c.kv("Payment Mode:", pay_mode, f)
        if pay_mode != "Cash":
            c.kv("Transaction ID:", f"TXN{rng.randint(10**9, 10**10 - 1)}", f)
    c.gap(40)
    c.text("Authorized Signatory & Stamp", font("sans", 15), align="right", color=(120, 120, 120))

    img = _apply_post(c.finish(), variations, rng, ctx, "medical_bill")
    gt = {
        "doc_type": "medical_bill",
        "variations": variations,
        "ground_truth": {
            "hospital_name": ctx.clinic_name,
            "bill_number": bill_no,
            "bill_date": ctx.consultation_date,
            "patient_name": ctx.patient_name,
            "consultation_fee": float(consultation),
            "procedure_charges": float(sum(a for _, a in proc_items)),
            "other_charges": float(sum(a for _, a in test_items) + medicine_charge),
            "total_amount": float(total),
            "line_items": [f"{lbl.strip()}: ₹{amt}" for lbl, amt in line_items],
            "payment_mode": pay_mode,
        },
        "extras": {
            "subtotal": subtotal, "gst": gst,
            "cancelled_item": cancelled[0] if cancelled else None,
            "refund": refund[1] if refund else None,
            "family_members": ctx.family_members or None,
        },
    }
    return img, gt


# ── 3. Diagnostic test report ────────────────────────────────────────────────

def generate_diagnostic_report(ctx: ClaimContext | None = None,
                               variations: list[str] | None = None,
                               rng: random.Random | None = None):
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "diagnostic_report")

    # Choose panels: those advised in the prescription that actually have ranges,
    # else a default CBC.
    paneled = [t for t in ctx.tests if data.TEST_PANELS.get(t)]
    if not paneled:
        paneled = ["Complete Blood Count (CBC)"]
    lab_name = rng.choice(data.LAB_NAMES)
    pathologist = "Dr. " + rng.choice(["Nanda", "Krishnan", "Verghese", "Saxena", "Bose"])
    report_id = f"RPT{rng.randint(100000, 999999)}"

    c = Canvas()
    c.text(lab_name, font("sans_bold", 32), align="center", color=(20, 90, 80))
    acc = data.accreditation(rng)
    c.text(acc, font("sans", 16), align="center", color=(80, 80, 80))
    c.text(ctx.clinic_address, font("sans", 14), align="center", color=(110, 110, 110))
    c.rule()

    f = font("sans", 17)
    c.row([f"Patient: {ctx.patient_name}", f"Report ID: {report_id}"], [0, 560], f)
    c.row([f"Age/Sex: {ctx.age}/{ctx.sex[0]}", f"Date: {ctx.consultation_date}"], [0, 560], f)
    c.kv("Ref. By:", ctx.doctor_name, f)
    c.rule(dashed=True)

    head = font("mono_bold", 17)
    c.row(["TEST NAME", "RESULT", "UNIT", "NORMAL RANGE"], [0, 360, 520, 660], head)
    c.rule(dashed=True)

    tests_performed: list[str] = []
    abnormal: list[str] = []
    mono = font("mono", 17)
    for panel in paneled:
        rows = data.TEST_PANELS.get(panel) or []
        tests_performed.append(panel)
        c.text(panel.upper(), font("mono_bold", 17), color=(20, 90, 80))
        if not rows:
            c.text("   See attached imaging / qualitative report.", mono, color=(90, 90, 90))
            continue
        for name, unit, (lo, hi) in rows:
            make_abnormal = rng.random() < 0.28
            if isinstance(lo, float) or isinstance(hi, float):
                val = (round(rng.uniform(hi, hi * 1.4), 1) if make_abnormal
                       else round(rng.uniform(lo, hi), 1))
            else:
                val = (rng.randint(int(hi), int(hi * 1.4)) if make_abnormal
                       else rng.randint(int(lo), int(hi)))
            flag = ""
            if val > hi:
                flag, color = " H", (170, 40, 40)
            elif val < lo:
                flag, color = " L", (170, 40, 40)
            else:
                color = (20, 20, 20)
            rng_str = f"{lo} - {hi}"
            c.row([f"  {name}", f"{val}{flag}", unit, rng_str], [0, 360, 520, 660],
                  mono, color=color)
            if flag.strip():
                abnormal.append(f"{name}: {val} {unit} ({flag.strip()}, ref {rng_str})")
        c.gap(6)

    c.rule(dashed=True)
    remark = ("All parameters within normal limits." if not abnormal
              else "Abnormal values flagged (H/L). Clinical correlation advised.")
    c.kv("Remarks:", remark, f)
    c.gap(30)
    c.kv("Pathologist:", pathologist, f)
    c.text("(Digitally Signed)", font("sans", 14), align="right", color=(120, 120, 120))

    img = _apply_post(c.finish(), variations, rng, ctx, "diagnostic_report")
    gt = {
        "doc_type": "diagnostic_report",
        "variations": variations,
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
    return img, gt


# ── 4. Pharmacy bill ─────────────────────────────────────────────────────────

def generate_pharmacy_bill(ctx: ClaimContext | None = None,
                          variations: list[str] | None = None,
                          rng: random.Random | None = None):
    rng = rng or random.Random()
    ctx = ctx or ClaimContext.random(rng)
    variations = variations if variations is not None else _pick_variations(rng, "pharmacy_bill")

    pharmacy = rng.choice(data.PHARMACY_NAMES)
    bill_no = data.bill_number(rng, "PH")
    dl = data.drug_license(rng)

    rows = []                       # (sno, name, batch, exp, qty, mrp, amount)
    purchased = []
    for i, med in enumerate(ctx.medicines, 1):
        mrp = data.MEDICINE_PRICES.get(med, rng.randint(3, 40))
        qty = rng.choice([5, 10, 14, 15, 20, 30])
        amt = mrp * qty
        batch = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2)) + str(rng.randint(100, 999))
        exp = f"{rng.randint(1, 12):02d}/{rng.randint(25, 28)}"
        rows.append((str(i), med, batch, exp, str(qty), str(mrp), f"{amt}"))
        purchased.append(f"{med} x{qty} - ₹{amt}")

    subtotal = sum(int(r[6]) for r in rows)
    gst = round(subtotal * 0.12)            # most medicines fall in 12% GST slab
    net = subtotal + gst

    c = Canvas(width=1050)
    c.text(pharmacy, font("sans_bold", 32), align="center", color=(30, 90, 30))
    c.text(f"Drug License No: {dl}", font("sans", 15), align="center", color=(80, 80, 80))
    c.text(f"GST No: {data.gst_number(rng)}", font("sans", 15), align="center", color=(80, 80, 80))
    c.text(ctx.clinic_address, font("sans", 14), align="center", color=(110, 110, 110))
    c.rule()

    f = font("sans", 17)
    c.row([f"Bill No: {bill_no}", f"Date: {ctx.consultation_date}"], [0, 620], f)
    c.kv("Patient:", ctx.patient_name, f)
    c.kv("Doctor:", ctx.doctor_name, f)
    c.rule(dashed=True)

    xs = [0, 70, 470, 620, 720, 800, 890]
    c.row(["S.No", "Medicine", "Batch", "Exp", "Qty", "MRP", "Amount"], xs,
          font("mono_bold", 16))
    c.rule(dashed=True)
    mono = font("mono", 16)
    for r in rows:
        c.row(list(r), xs, mono)
    c.rule(dashed=True)
    c.row(["", "", "", "", "", "Total", f"{subtotal}"], xs, font("mono_bold", 16))
    c.row(["", "", "", "", "", "GST", f"{gst}"], xs, mono)
    c.row(["", "", "", "", "", "Net", f"{net}"], xs, font("mono_bold", 18),
          color=(25, 55, 110))
    c.gap(40)
    c.text("Pharmacist Signature & Stamp", font("sans", 15), align="right", color=(120, 120, 120))

    img = _apply_post(c.finish(), variations, rng, ctx, "pharmacy_bill")
    gt = {
        "doc_type": "pharmacy_bill",
        "variations": variations,
        "ground_truth": {
            "pharmacy_name": pharmacy,
            "drug_license": dl,
            "bill_date": ctx.consultation_date,
            "patient_name": ctx.patient_name,
            "doctor_name": ctx.doctor_name,
            "medicines_purchased": purchased,
            "total_amount": float(net),
        },
        "extras": {"subtotal": subtotal, "gst": gst},
    }
    return img, gt


# ── High-level helpers ───────────────────────────────────────────────────────

_GENERATORS = {
    "prescription": generate_prescription,
    "medical_bill": generate_medical_bill,
    "diagnostic_report": generate_diagnostic_report,
    "pharmacy_bill": generate_pharmacy_bill,
}

# Lazily imported to avoid circular imports; populated on first use.
_PDF_GENERATORS: dict | None = None


def _get_pdf_generators() -> dict:
    global _PDF_GENERATORS
    if _PDF_GENERATORS is None:
        from .pdf_generator import _PDF_GENERATORS as _pdg
        _PDF_GENERATORS = _pdg
    return _PDF_GENERATORS


def _save(img: Image.Image | None, pdf_bytes: bytes | None,
          gt: dict, out_dir: Path, stem: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    record: dict = {}
    if img is not None:
        img_path = out_dir / f"{stem}.png"
        img.save(img_path)
        record["image"] = str(img_path)
    if pdf_bytes is not None:
        pdf_path = out_dir / f"{stem}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        record["pdf"] = str(pdf_path)
    (out_dir / f"{stem}.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False))
    return {**record, **gt}


def _generate_one(doc_type: str, ctx: ClaimContext, rng: random.Random,
                  fmt: str) -> tuple[Image.Image | None, bytes | None, dict]:
    """Generate PNG and/or PDF for one document type, resetting rng state so
    both formats receive identical random draws."""
    if fmt == "png":
        img, gt = _GENERATORS[doc_type](ctx=ctx, rng=rng)
        return img, None, gt
    if fmt == "pdf":
        pdf_bytes, gt = _get_pdf_generators()[doc_type](ctx=ctx, rng=rng)
        return None, pdf_bytes, gt
    # fmt == "both": generate PNG first, then reset rng so PDF gets same draws.
    pre_state = rng.getstate()
    img, gt = _GENERATORS[doc_type](ctx=ctx, rng=rng)
    post_png_state = rng.getstate()
    rng.setstate(pre_state)
    pdf_bytes, _ = _get_pdf_generators()[doc_type](ctx=ctx, rng=rng)
    rng.setstate(post_png_state)   # resume PNG's rng trajectory for next doc
    return img, pdf_bytes, gt


def generate_claim_set(out_dir: str | Path = "generated_documents/claim",
                       seed: int | None = None,
                       fmt: str = "png") -> dict:
    """Generate all four documents for ONE coherent claim (shared patient,
    doctor, diagnosis, medicines and date).

    ``fmt`` is ``"png"`` (default), ``"pdf"``, or ``"both"``.
    Returns a manifest dict."""
    assert fmt in ("png", "pdf", "both"), f"fmt must be png/pdf/both, got {fmt!r}"
    rng = random.Random(seed)
    ctx = ClaimContext.random(rng)
    out_dir = Path(out_dir)
    manifest = {"claim_context": {
        "patient_name": ctx.patient_name, "doctor_name": ctx.doctor_name,
        "doctor_reg": ctx.doctor_reg, "diagnosis": ctx.diagnosis,
        "date": ctx.consultation_date, "medicines": ctx.medicines,
        "tests": ctx.tests, "procedure": ctx.procedure,
    }, "format": fmt, "documents": []}
    for doc_type in _GENERATORS:
        img, pdf_bytes, gt = _generate_one(doc_type, ctx, rng, fmt)
        manifest["documents"].append(_save(img, pdf_bytes, gt, out_dir, doc_type))
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def generate_batch(count: int = 25, out_dir: str | Path = "generated_documents",
                   seed: int | None = None, doc_types: list[str] | None = None,
                   fmt: str = "png") -> dict:
    """Generate ``count`` randomized standalone documents.

    ``fmt`` is ``"png"`` (default), ``"pdf"``, or ``"both"``.
    Returns a manifest dict."""
    assert fmt in ("png", "pdf", "both"), f"fmt must be png/pdf/both, got {fmt!r}"
    rng = random.Random(seed)
    out_dir = Path(out_dir)
    doc_types = doc_types or list(_GENERATORS)
    manifest: dict = {"count": count, "format": fmt, "documents": []}
    for i in range(count):
        doc_type = rng.choice(doc_types)
        img, pdf_bytes, gt = _generate_one(doc_type, None, rng, fmt)
        stem = f"{doc_type}_{i:03d}"
        manifest["documents"].append(_save(img, pdf_bytes, gt, out_dir, stem))
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest
