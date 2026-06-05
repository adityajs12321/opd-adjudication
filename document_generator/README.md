# Mock Medical Document Generator

Generates realistic **prescription**, **medical-bill/invoice**, **diagnostic-report**
and **pharmacy-bill** documents — as raster **PNG** images and/or text-based **PDF** —
for testing the OPD claim-adjudication pipeline.

It can generate **randomized standalone documents**, a **coherent 4-document claim set**
(shared patient/doctor/diagnosis), or a **prescription + bill for every scenario in
`../test_cases.json`** so the generated documents match the expected adjudication outcome.

Each generated document has a sidecar `*.json` holding the **ground truth** (mirroring
the extraction models in `backend/models.py`) plus the list of variations applied, so
you can diff Gemini's OCR/extraction against what was actually printed.

## Install

```bash
pip install -r document_generator/requirements.txt   # Pillow + numpy + reportlab
```

## Usage (CLI)

```bash
# PNG images (default)
python -m document_generator batch --count 25
python -m document_generator claim --out generated_documents/claim_demo

# Text-based PDFs (real selectable text, not image embeds)
python -m document_generator batch --count 25 --format pdf
python -m document_generator claim --format pdf

# Both PNG and PDF for each document (rng-matched: identical amounts/values)
python -m document_generator batch --count 25 --format both
python -m document_generator claim --format both

# Single document with explicit format + variations
python -m document_generator single --type prescription --format pdf \
    --variations handwritten stamp signature
python -m document_generator single --type medical_bill --format both \
    --variations stamp correction

# Prescription + bill for every scenario in ../test_cases.json
# (amounts come from each test case, so the docs match the expected decision)
python -m document_generator testcases --format both
python -m document_generator testcases --cases TC002 TC005   # only specific cases
python -m document_generator testcases --seed 7              # re-roll unpinned hospitals
```

Each test case is written to its own subdirectory (`tc001/`, `tc002/`, …) with a
per-case manifest, plus a top-level `manifest.json` listing every case and its expected
decision. `TC004` has no prescription in the source data, so only a bill is generated.

## Usage (Python)

```python
from document_generator import (
    generate_prescription, generate_medical_bill,
    generate_diagnostic_report, generate_pharmacy_bill,
    generate_claim_set, generate_batch, generate_test_cases,
)
from document_generator.pdf_generator import (
    generate_prescription_pdf, generate_medical_bill_pdf,
    generate_diagnostic_report_pdf, generate_pharmacy_bill_pdf,
)

# PNG
img, gt = generate_prescription(variations=["handwritten", "skewed"])
img.save("rx.png")

# PDF (real selectable text via reportlab)
pdf_bytes, gt = generate_prescription_pdf(variations=["stamp", "signature"])
open("rx.pdf", "wb").write(pdf_bytes)

# Both formats, identical document data (rng state reset between them)
generate_claim_set(out_dir="generated_documents/claim", seed=42, fmt="both")
generate_batch(count=30, out_dir="generated_documents", fmt="pdf")

# Documents for the test-case scenarios (optionally filtered by case id)
generate_test_cases(out_dir="generated_documents/test_cases", fmt="both",
                    case_ids=["TC002", "TC005"])
```

## Output files

Each generated document produces:
- `stem.png` (if fmt=png or both) — raster image with OCR variations
- `stem.pdf` (if fmt=pdf or both) — text-based PDF with vectorized stamps/signatures
- `stem.json` — ground truth matching `backend/models.py` extraction schemas

## Formats

**PNG** — raster images with visual OCR stressors (blur, skew, JPEG artifacts, …).
Good for testing Gemini's vision-based document extraction.

**PDF** — real text PDFs (reportlab `drawString`, WinAnsiEncoding for built-ins,
CID-encoding for TTF fonts). Text is fully selectable/searchable. Stamps and
signatures are drawn as PDF path/text objects. Good for testing a PDF text-extraction
path alongside the vision path.

**`--format both`** — each document generates a PNG and a PDF with identical data
(same amounts, dosages, lab values) via `rng.getstate()/setstate()` so both files
share the same GT JSON.

## Variations

Render-time: `handwritten` (italic font), `multilingual` (Hindi/Kannada/Tamil header).
Post-processing: `faded`, `blurry`, `skewed` (perspective + rotation), `noisy`,
`lowres` (JPEG artifacts), `stamp`, `signature`, `correction` (pen strike-through),
`partial` (truncated).

PDF-compatible: `handwritten`, `multilingual`, `stamp`, `signature`, `correction`.
Image-only (silently skipped for PDF): `faded`, `blurry`, `skewed`, `noisy`, `lowres`, `partial`.

Bills also include edge displays: **multiple patients** and **refunds** (random documents only,
since they change the named patient / total), plus **cancelled items** and **part payments**
(in random *and* test-case documents — both are total-preserving: a cancelled line is drawn
struck-through and never summed, and a part payment only splits the payment block, so neither
changes the billed total). Diagnostic reports flag out-of-range values with `H`/`L` markers.

## Bill layout templates

To exercise extraction against varied invoice formats, each medical bill renders in one of
three structurally distinct layouts. The layout is chosen **deterministically from the hospital
name** (stable hash), so the same hospital always looks the same while different hospitals differ:

| Template | Header | GST line | Columns | Total label | Amount style |
|---|---|---|---|---|---|
| `classic`  | centered | yes | `PARTICULARS / AMOUNT (Rs.)`     | `TOTAL`       | `1,500`    |
| `compact`  | left     | no  | `Description / Charges (INR)`    | `Net Payable` | `Rs. 1,500`|
| `itemised` | centered | yes (+ `TAX INVOICE`) | numbered `SR PARTICULARS / AMOUNT` | `GRAND TOTAL` | `1,500.00` |

Set a document's hospital to control its layout: `ClaimContext(clinic_name=...)` for the Python
API, the `hospital` field of a case's `input_data` in `test_cases.json` for the `testcases`
command, or a random clinic name otherwise. Any string works — even a custom hospital name maps
to one of the three templates.
