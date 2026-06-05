"""Sample data pools used to populate generated documents.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field

# ── Reference pools ──────────────────────────────────────────────────────────

STATE_CODES = ["KA", "MH", "DL", "TN", "GJ", "AP", "UP", "WB", "KL", "RJ"]

PATIENT_NAMES = [
    "Rajesh Kumar", "Priya Singh", "Amit Verma", "Sneha Reddy", "Vikram Joshi",
    "Kavita Nair", "Suresh Patil", "Ravi Menon", "Anita Desai", "Deepak Shah",
    "Meera Iyer", "Arjun Rao", "Pooja Gupta", "Sanjay Mishra", "Divya Pillai",
    "Rohan Kapoor", "Nisha Banerjee", "Karthik Subramaniam", "Fatima Sheikh",
    "Harpreet Kaur",
]

DOCTOR_NAMES = [
    "Dr. Sharma", "Dr. Patel", "Dr. Gupta", "Dr. Mehta", "Dr. Rao",
    "Dr. Khan", "Dr. Banerjee", "Dr. Iyer", "Dr. Reddy", "Dr. Nair",
    "Dr. Deshpande", "Dr. Chakraborty", "Dr. Krishnan", "Dr. Bhatia",
]

QUALIFICATIONS = [
    "MBBS, MD (General Medicine)",
    "MBBS, MD (Internal Medicine)",
    "MBBS, DNB",
    "MBBS, MD, DM (Cardiology)",
    "MBBS, MS (Ortho)",
    "MBBS, DCH (Paediatrics)",
    "BDS, MDS",
]

CLINIC_NAMES = [
    "Sunrise Medical Centre", "City Care Clinic", "LifeLine Polyclinic",
    "Wellness Family Clinic", "Apollo Hospitals", "Fortis Healthcare",
    "Manipal Clinic", "Sparsh Multispeciality Hospital", "Aarogya Nursing Home",
    "Sanjeevani Health Centre",
]

NETWORK_HOSPITALS = ["Apollo Hospitals", "Fortis Healthcare", "Manipal Clinic"]

LAB_NAMES = [
    "Metropolis Diagnostics", "SRL Diagnostics", "Dr. Lal PathLabs",
    "Thyrocare Centre", "Vijaya Diagnostics", "Quest Pathology Lab",
    "Aarogya Diagnostic Centre",
]

PHARMACY_NAMES = [
    "Apollo Pharmacy", "MedPlus", "Wellness Forever", "Generic Aadhaar Medicals",
    "City Chemists", "HealthFirst Pharmacy", "Janata Medical Store",
]

CITIES = [
    ("Bengaluru", "Karnataka", "560001"),
    ("Mumbai", "Maharashtra", "400001"),
    ("New Delhi", "Delhi", "110001"),
    ("Chennai", "Tamil Nadu", "600001"),
    ("Pune", "Maharashtra", "411001"),
    ("Hyderabad", "Telangana", "500001"),
    ("Kochi", "Kerala", "682001"),
]

STREETS = [
    "MG Road", "Brigade Road", "Linking Road", "Anna Salai", "FC Road",
    "Jubilee Hills", "Park Street", "Residency Road", "Sector 14",
]

# (diagnosis, [medicines], [tests], optional procedure)
CONDITIONS = [
    ("Viral fever", ["Paracetamol 650mg", "Vitamin C", "Cetirizine 10mg"],
     ["Complete Blood Count (CBC)", "Dengue NS1 Antigen"], None),
    ("Upper respiratory tract infection", ["Azithromycin 500mg", "Cetirizine 10mg"],
     ["Complete Blood Count (CBC)"], None),
    ("Gastroenteritis", ["Ofloxacin 200mg", "Probiotics", "ORS"],
     ["Stool Routine", "Complete Blood Count (CBC)"], None),
    ("Hypertension", ["Amlodipine 5mg", "Telmisartan 40mg"],
     ["ECG", "Lipid Profile", "Kidney Function Test (KFT)"], None),
    ("Type 2 Diabetes", ["Metformin 500mg", "Glimepiride 1mg"],
     ["Blood Sugar (Fasting/PP)", "HbA1c"], None),
    ("Migraine", ["Sumatriptan 50mg", "Propranolol 40mg"],
     [], None),
    ("Allergic rhinitis", ["Cetirizine 10mg", "Montelukast 10mg"],
     [], None),
    ("Lower back pain", ["Aceclofenac 100mg", "Thiocolchicoside 4mg"],
     ["X-Ray Lumbar Spine"], "Physiotherapy"),
    ("Acute bronchitis", ["Amoxicillin 500mg", "Salbutamol Inhaler"],
     ["X-Ray Chest"], None),
    ("Tooth decay requiring root canal", ["Amoxicillin 500mg", "Ibuprofen 400mg"],
     [], "Root canal treatment"),
]

# Medicine -> approx MRP per unit (INR). Used for pharmacy bills.
MEDICINE_PRICES = {
    "Paracetamol 650mg": 3, "Paracetamol 500mg": 2, "Vitamin C": 4,
    "Cetirizine 10mg": 3, "Azithromycin 500mg": 28, "Ofloxacin 200mg": 12,
    "Probiotics": 18, "ORS": 22, "Amlodipine 5mg": 5, "Telmisartan 40mg": 9,
    "Metformin 500mg": 4, "Glimepiride 1mg": 6, "Sumatriptan 50mg": 45,
    "Propranolol 40mg": 4, "Montelukast 10mg": 14, "Aceclofenac 100mg": 6,
    "Thiocolchicoside 4mg": 22, "Amoxicillin 500mg": 11, "Salbutamol Inhaler": 130,
    "Ibuprofen 400mg": 3, "Omeprazole 20mg": 5,
}

# Diagnostic test -> (result, normal_range, unit, abnormal?)  used by report panels.
TEST_PANELS = {
    "Complete Blood Count (CBC)": [
        ("Hemoglobin", "g/dL", (13.0, 17.0)),
        ("WBC Count", "/cu.mm", (4000, 11000)),
        ("Platelet Count", "/cu.mm", (150000, 450000)),
        ("RBC Count", "mill/cu.mm", (4.5, 5.5)),
    ],
    "Liver Function Test (LFT)": [
        ("SGPT (ALT)", "U/L", (10, 40)),
        ("SGOT (AST)", "U/L", (10, 40)),
        ("Total Bilirubin", "mg/dL", (0.3, 1.2)),
    ],
    "Lipid Profile": [
        ("Total Cholesterol", "mg/dL", (125, 200)),
        ("Triglycerides", "mg/dL", (50, 150)),
        ("HDL Cholesterol", "mg/dL", (40, 60)),
    ],
    "Blood Sugar (Fasting/PP)": [
        ("Fasting Blood Sugar", "mg/dL", (70, 100)),
        ("Post Prandial Sugar", "mg/dL", (70, 140)),
    ],
    "HbA1c": [("HbA1c", "%", (4.0, 5.6))],
    "Kidney Function Test (KFT)": [
        ("Blood Urea", "mg/dL", (15, 40)),
        ("Serum Creatinine", "mg/dL", (0.6, 1.3)),
    ],
    "Thyroid Profile": [
        ("TSH", "uIU/mL", (0.4, 4.0)),
        ("T3", "ng/dL", (80, 200)),
        ("T4", "ug/dL", (5.0, 12.0)),
    ],
    "Urine Routine": [],
    "Dengue NS1 Antigen": [],
    "Stool Routine": [],
    "ECG": [],
    "X-Ray Chest": [],
    "X-Ray Lumbar Spine": [],
}

PAYMENT_MODES = ["Cash", "Card", "UPI"]

# Regional-language label snippets for the "multilingual" variation.
MULTILINGUAL_TAGLINES = {
    "hi": ("स्वास्थ्य ही धन है", "रोगी का नाम", "कुल राशि"),       # Devanagari (Hindi)
    "kn": ("ಆರೋಗ್ಯವೇ ಭಾಗ್ಯ", "ರೋಗಿಯ ಹೆಸರು", "ಒಟ್ಟು ಮೊತ್ತ"),     # Kannada
    "ta": ("உடல்நலமே செல்வம்", "நோயாளியின் பெயர்", "மொத்தம்"),     # Tamil
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def reg_number(rng: random.Random) -> str:
    """e.g. 'KA/45678/2015'."""
    return f"{rng.choice(STATE_CODES)}/{rng.randint(10000, 99999)}/{rng.randint(2008, 2022)}"


def gst_number(rng: random.Random) -> str:
    state = rng.randint(1, 37)
    letters = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(5))
    return f"{state:02d}{letters}{rng.randint(1000, 9999)}{rng.choice('ABCDEFGHJ')}1Z{rng.randint(0, 9)}"


def drug_license(rng: random.Random) -> str:
    return f"{rng.choice(STATE_CODES)}-{rng.randint(20000, 99999)}-{rng.choice('AB')}"


def accreditation(rng: random.Random) -> str:
    return f"NABL: MC-{rng.randint(1000, 9999)}"


def address(rng: random.Random) -> str:
    city, state, pin = rng.choice(CITIES)
    return f"{rng.randint(1, 250)}, {rng.choice(STREETS)}, {city}, {state} - {pin}"


def phone(rng: random.Random) -> str:
    return f"+91 {rng.randint(70, 99)}{rng.randint(10, 99)} {rng.randint(100000, 999999)}"


def bill_number(rng: random.Random, prefix: str = "INV") -> str:
    return f"{prefix}-{rng.randint(2024, 2024)}-{rng.randint(10000, 99999)}"


def amount_in_words(amount: int) -> str:
    """Very small int->words converter for INR (handles up to lakhs)."""
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
            "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
            "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
            "Eighty", "Ninety"]

    def two(n: int) -> str:
        if n < 20:
            return ones[n]
        return (tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")).strip()

    def three(n: int) -> str:
        h, rest = divmod(n, 100)
        out = (ones[h] + " Hundred" if h else "")
        if rest:
            out += (" " if out else "") + two(rest)
        return out

    if amount == 0:
        return "Zero Rupees Only"
    parts = []
    lakh, rest = divmod(amount, 100000)
    thousand, rest = divmod(rest, 1000)
    if lakh:
        parts.append(two(lakh) + " Lakh")
    if thousand:
        parts.append(two(thousand) + " Thousand")
    if rest:
        parts.append(three(rest))
    return " ".join(parts).strip() + " Rupees Only"


# ── Bill layout templates ─────────────────────────────────────────────────────

# Each hospital deterministically maps to ONE bill template (by a stable hash of
# its name), so the same hospital always renders with the same structure while
# different hospitals look visibly distinct — exercising the extraction agent
# against varied invoice formats rather than one fixed layout.
_BILL_TEMPLATE_SPECS = {
    "classic": {
        "header_align": "center",
        "show_gst": True,
        "caption": None,
        "patient_label": "Patient Details:",
        "col_header": ("PARTICULARS", "AMOUNT (Rs.)"),
        "numbered": False,
        "total_label": "TOTAL",
        "amount_fmt": "comma",       # 1,500
        "footer": "Authorized Signatory & Stamp",
    },
    "compact": {
        "header_align": "left",
        "show_gst": False,
        "caption": None,
        "patient_label": "Bill To:",
        "col_header": ("Description", "Charges (INR)"),
        "numbered": False,
        "total_label": "Net Payable",
        "amount_fmt": "rupee",       # Rs. 1,500
        "footer": "For {hospital}",
    },
    "itemised": {
        "header_align": "center",
        "show_gst": True,
        "caption": "TAX INVOICE",
        "patient_label": "Patient:",
        "col_header": ("SR  PARTICULARS", "AMOUNT"),
        "numbered": True,
        "total_label": "GRAND TOTAL",
        "amount_fmt": "decimal",     # 1,500.00
        "footer": "Authorized Signatory & Stamp",
    },
}

_BILL_TEMPLATE_ORDER = ("classic", "compact", "itemised")

# Plausible line items shown as a struck-through CANCELLED row (never summed).
CANCELLED_ITEM_POOL = [
    "Lipid Profile", "Vitamin D (25-OH)", "X-Ray Chest", "ECG",
    "Urine Routine", "Thyroid Profile",
]


def bill_template_spec(hospital_name: str) -> dict:
    """Deterministically pick a bill template spec from the hospital name."""
    h = int(hashlib.md5((hospital_name or "").encode("utf-8")).hexdigest(), 16)
    return _BILL_TEMPLATE_SPECS[_BILL_TEMPLATE_ORDER[h % len(_BILL_TEMPLATE_ORDER)]]


def fmt_amount(amount: int, style: str = "comma") -> str:
    """Format a rupee amount according to a template's amount style."""
    neg = amount < 0
    a = abs(int(amount))
    if style == "rupee":
        s = f"Rs. {a:,}"
    elif style == "decimal":
        s = f"{a:,}.00"
    else:  # comma
        s = f"{a:,}"
    return f"-{s}" if neg else s


# ── Coherent claim context shared across a 4-document set ─────────────────────

@dataclass
class ClaimContext:
    """Ground-truth facts shared by every document in one claim."""
    patient_name: str
    age: int
    sex: str
    patient_address: str
    doctor_name: str
    doctor_qualification: str
    doctor_reg: str
    clinic_name: str
    clinic_address: str
    clinic_phone: str
    diagnosis: str
    complaints: list[str]
    medicines: list[str]
    tests: list[str]
    procedure: str | None
    consultation_date: str          # DD/MM/YYYY
    follow_up_date: str             # DD/MM/YYYY
    language: str = "en"            # 'en' or a regional code for multilingual docs
    family_members: list[str] = field(default_factory=list)

    @classmethod
    def from_test_case(cls, tc: dict, rng: "random.Random") -> "ClaimContext":
        """Build a ClaimContext from a test_cases.json entry."""
        from datetime import datetime
        inp = tc["input_data"]
        docs = inp.get("documents", {})
        rx = docs.get("prescription", {})
        bill = docs.get("bill", {})

        raw_date = inp.get("treatment_date", "")
        if raw_date:
            d = datetime.strptime(raw_date, "%Y-%m-%d")
            consultation_date = d.strftime("%d/%m/%Y")
            follow_up_date = f"{min(d.day + 7, 28):02d}/{d.month:02d}/{d.year}"
        else:
            day, month = rng.randint(1, 28), rng.randint(1, 12)
            consultation_date = f"{day:02d}/{month:02d}/2024"
            follow_up_date = f"{min(day + 7, 28):02d}/{month:02d}/2024"

        medicines = rx.get("medicines_prescribed") or rx.get("medicines") or []
        tests = rx.get("tests_prescribed") or bill.get("test_names") or []

        procedure = None
        procs = rx.get("procedures")
        if procs:
            procedure = ", ".join(procs) if isinstance(procs, list) else procs
        elif rx.get("treatment"):
            procedure = rx["treatment"]

        complaints_pool = [
            "Fever since 3 days", "Body ache", "Headache", "Cough and cold",
            "Loose motions", "Fatigue", "Loss of appetite", "Joint pain",
        ]
        # Use complaints supplied in the test case if present, else sample the pool.
        complaints = rx.get("complaints") or rng.sample(complaints_pool, k=rng.randint(2, 3))

        return cls(
            patient_name=inp["member_name"],
            age=rng.randint(25, 65),
            sex=rng.choice(["Male", "Female"]),
            patient_address=address(rng),
            doctor_name=rx.get("doctor_name") or rng.choice(DOCTOR_NAMES),
            doctor_qualification=rng.choice(QUALIFICATIONS),
            doctor_reg=rx.get("doctor_reg") or reg_number(rng),
            clinic_name=inp.get("hospital") or rng.choice(CLINIC_NAMES),
            clinic_address=address(rng),
            clinic_phone=phone(rng),
            diagnosis=rx.get("diagnosis") or "General consultation",
            complaints=complaints,
            medicines=medicines,
            tests=tests,
            procedure=procedure,
            consultation_date=consultation_date,
            follow_up_date=follow_up_date,
        )

    @classmethod
    def random(cls, rng: random.Random) -> "ClaimContext":
        diagnosis, meds, tests, proc = rng.choice(CONDITIONS)
        sex = rng.choice(["Male", "Female"])
        day = rng.randint(1, 28)
        month = rng.randint(1, 12)
        complaints_pool = [
            "Fever since 3 days", "Body ache", "Headache", "Cough and cold",
            "Loose motions", "Fatigue", "Loss of appetite", "Joint pain",
            "Sore throat", "Vomiting", "Dizziness", "Chest discomfort",
        ]
        return cls(
            patient_name=rng.choice(PATIENT_NAMES),
            age=rng.randint(5, 78),
            sex=sex,
            patient_address=address(rng),
            doctor_name=rng.choice(DOCTOR_NAMES),
            doctor_qualification=rng.choice(QUALIFICATIONS),
            doctor_reg=reg_number(rng),
            clinic_name=rng.choice(CLINIC_NAMES),
            clinic_address=address(rng),
            clinic_phone=phone(rng),
            diagnosis=diagnosis,
            complaints=rng.sample(complaints_pool, k=rng.randint(2, 3)),
            medicines=meds,
            tests=tests,
            procedure=proc,
            consultation_date=f"{day:02d}/{month:02d}/2024",
            follow_up_date=f"{min(day + 7, 28):02d}/{month:02d}/2024",
        )
