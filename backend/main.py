import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

import database as db
import graph_store
from models import (
    AdjudicationDecision,
    DocumentAdjudicationResponse,
    ExtractedDiagnosticReport,
    ExtractedMedicalBill,
    ExtractedPharmacyBill,
    ExtractedPrescription,
    ExtractionResults,
    MemberCreate,
    MemberRecord,
)

load_dotenv()

app = FastAPI(title="Plum OPD Adjudication API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

ROOT = Path(__file__).parent.parent
_policy = (ROOT / "policy_terms.json").read_text()
_policy_data: dict = json.loads(_policy)
_rules = (ROOT / "adjudication_rules.json").read_text()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


@app.on_event("startup")
def startup():
    db.init_db()
    graph_store.init_graph(_policy_data)


# ── Extraction prompts (one per document agent) ──────────────────────────────

PRESCRIPTION_PROMPT = """You are a medical document extraction agent specializing in prescriptions.
Extract all information from this prescription and return JSON with these exact fields:
{
  "doctor_name": "full name",
  "doctor_registration": "registration number like KA/45678/2015",
  "patient_name": "patient full name",
  "consultation_date": "YYYY-MM-DD",
  "diagnosis": "primary diagnosis exactly as written",
  "canonical_conditions": ["normalised condition names — map the diagnosis to any that apply from this fixed list: diabetes, hypertension, joint_replacement, maternity, pre_existing_disease. Use the exact strings from the list. Examples: 'Type 2 DM' -> ['diabetes'], 'HTN' -> ['hypertension'], 'T2DM with hypertension' -> ['diabetes', 'hypertension']. Empty array if none apply."],
  "medicines_prescribed": ["Medicine Name Dose - Duration"],
  "tests_advised": ["Test Name"],
  "procedures": ["procedure name if any"],
  "notes": "any other clinical notes"
}
Use empty string for missing text fields and empty arrays for missing lists."""

MEDICAL_BILL_PROMPT = """You are a medical document extraction agent specializing in hospital bills.
Extract all information from this bill/invoice and return JSON with these exact fields:
{
  "hospital_name": "hospital or clinic name",
  "bill_number": "bill or invoice number",
  "bill_date": "YYYY-MM-DD",
  "patient_name": "patient name",
  "consultation_fee": 0.0,
  "procedure_charges": 0.0,
  "other_charges": 0.0,
  "total_amount": 0.0,
  "line_items": ["Item: ₹Amount"],
  "payment_mode": "Cash/Card/UPI/etc"
}
Use 0 for missing numeric fields and empty arrays/strings for missing text."""

DIAGNOSTIC_PROMPT = """You are a medical document extraction agent specializing in diagnostic reports.
Extract all information from this lab/diagnostic report and return JSON with these exact fields:
{
  "lab_name": "laboratory name",
  "accreditation": "NABL/CAP accreditation number if present",
  "report_date": "YYYY-MM-DD",
  "patient_name": "patient name",
  "tests_performed": ["Test Name - Result (Normal Range)"],
  "abnormal_findings": ["Test Name - abnormal value"],
  "pathologist": "pathologist name",
  "summary": "overall interpretation or remarks"
}
Use empty string for missing text fields and empty arrays for missing lists."""

PHARMACY_BILL_PROMPT = """You are a medical document extraction agent specializing in pharmacy bills.
Extract all information from this pharmacy/chemist bill and return JSON with these exact fields:
{
  "pharmacy_name": "pharmacy name",
  "drug_license": "drug license number",
  "bill_date": "YYYY-MM-DD",
  "patient_name": "patient name",
  "doctor_name": "prescribing doctor name",
  "medicines_purchased": ["Medicine Name Qty x Pack - ₹Amount"],
  "total_amount": 0.0
}
Use empty string for missing text fields, empty arrays for lists, and 0 for missing amounts."""

# ── Adjudication system prompt ───────────────────────────────────────────────
# Split into a static base (rules, constraints — built once at startup) and a
# dynamic policy context block appended per-claim from the Neo4j graph query.

_ADJUDICATION_BASE_PROMPT = f"""You are an expert OPD insurance claim adjudicator for Plum Insurance.

The input you receive includes `rule_engine_findings` — the output of a deterministic rule engine
that has already evaluated all numerical and date-based rules. Your job is to handle the
non-deterministic aspects that require judgment:

1. **Document validity**: Are prescriptions authentic? Doctor registration format valid ([State]/[Number]/[Year])? Dates consistent across documents?
2. **Medical necessity**: Does the diagnosis justify the treatment, tests, and medicines?
3. **Coverage verification**: Is the condition/service covered or excluded under the policy?
4. **Fraud detection**: Flag any suspicious patterns from the fraud indicators list.

## YOUR CONSTRAINTS (from the rule engine — do not override):
- `rule_engine_findings.hard_rejections`: Definitive. Include every code in `rejection_reasons`.
- `rule_engine_findings.amount_analysis.max_approvable`: The computed ceiling. Never set `approved_amount` higher than this value.
- `rule_engine_findings.deductions`: Already calculated. Carry them into the `deductions` field.
- `rule_engine_findings.pre_auth_flags`: Tests requiring pre-authorization — flag if not confirmed.
- `rule_engine_findings.suggested_decision`: The deterministic baseline decision. Rules:
  - Copay is a normal cost-share — a claim with copay deductions is still APPROVED, NOT partial.
  - PARTIAL applies only when (a) amounts were capped by limits, or (b) you determine that SOME treatments/items are covered while others are excluded or not medically necessary.
  - You may DOWNGRADE the suggested decision (APPROVED -> PARTIAL -> REJECTED -> MANUAL_REVIEW) based on coverage, medical necessity, or fraud judgment.
  - You may NOT UPGRADE it (e.g. never return APPROVED when suggested_decision is PARTIAL because of a limit cap).

## ADJUDICATION RULES
```json
{_rules}
```

Return a JSON object with ALL of these fields:
- claim_id (string)
- decision: "APPROVED", "REJECTED", "PARTIAL", or "MANUAL_REVIEW"
- approved_amount (number — must not exceed rule_engine_findings.amount_analysis.max_approvable)
- rejection_reasons (array of rejection codes — ONLY populate for decision="REJECTED". Must be empty [] for APPROVED, PARTIAL, and MANUAL_REVIEW. For REJECTED, include all codes from rule_engine_findings.hard_rejections)
- confidence_score (number 0.0–1.0)
- notes (string)
- next_steps (string)
"""


def _build_system_prompt(policy_context: dict) -> str:
    """Append the graph-retrieved policy context to the static base prompt."""
    return (
        _ADJUDICATION_BASE_PROMPT
        + "\n\n## RELEVANT POLICY TERMS (retrieved from policy graph for this claim)\n"
        + "```json\n"
        + json.dumps(policy_context, indent=2)
        + "\n```"
    )


# ── Rule engine: deterministic pre-processing ────────────────────────────────

_DOCTOR_REG_RE = re.compile(r"^[A-Z]{2,3}/\d+/\d{4}$")


def run_rule_engine(
    extractions: ExtractionResults,
    member_join_date: str,
    member_found: bool,
    member_active: bool,
    annual_spend: float,
    is_duplicate: bool,
    claimed_amount: float = 0,
) -> dict:
    policy = _policy_data
    limits = policy["coverage_details"]
    claim_reqs = policy["claim_requirements"]
    network_hospitals = [h.lower() for h in policy["network_hospitals"]]
    today = date.today()

    hard_rejections: list[dict] = []
    warnings: list[dict] = []
    deductions: dict[str, float] = {}
    amount_analysis: dict = {}
    pre_auth_flags: list[str] = []
    waiting_period_checks: list[dict] = []

    # ── Collect uploaded document references ─────────────────────────────────

    bill = extractions.medical_bill
    rx = extractions.prescription
    pharmacy = extractions.pharmacy_bill
    diagnostic = extractions.diagnostic_report

    # ── Eligibility ───────────────────────────────────────────────────────────

    if not member_found:
        hard_rejections.append({
            "code": "MEMBER_NOT_COVERED",
            "reason": "Member ID not found in the policy records.",
        })
    elif not member_active:
        hard_rejections.append({
            "code": "MEMBER_NOT_COVERED",
            "reason": "Member exists but is marked inactive in the policy records.",
        })

    if is_duplicate:
        hard_rejections.append({
            "code": "DUPLICATE_CLAIM",
            "reason": "A claim with the same bill number or treatment date and hospital already exists for this member.",
        })

    # ── Documentation: missing documents ─────────────────────────────────────

    # A prescription from a registered doctor is required for every OPD claim.
    if rx is None:
        if pharmacy is not None:
            reason = "Pharmacy bill submitted without a prescription. A valid prescription is required to process pharmacy claims."
        else:
            reason = "No prescription was uploaded. A valid prescription from a registered doctor is required to process the claim."
        hard_rejections.append({
            "code": "MISSING_DOCUMENTS",
            "reason": reason,
        })

    # Prescription without any financial document — no amount to approve
    if rx is not None and bill is None and pharmacy is None:
        warnings.append({
            "code": "MISSING_DOCUMENTS",
            "reason": "Prescription uploaded but no medical bill or pharmacy bill provided. No claimable amount can be determined.",
        })

    # ── Documentation: illegible / incomplete extraction ─────────────────────
    # Check each uploaded document for individually missing critical fields.
    # Any single required field missing flags the document — not just all-empty.

    if rx is not None:
        missing = []
        if not rx.diagnosis:
            missing.append("diagnosis")
        if not rx.medicines_prescribed and not rx.tests_advised:
            missing.append("medicines or tests prescribed")
        if missing:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": f"Prescription is missing required fields: {', '.join(missing)}.",
            })

    if bill is not None:
        missing = []
        if bill.total_amount == 0:
            missing.append("total amount")
        if not bill.bill_date:
            missing.append("bill date")
        if not bill.hospital_name:
            missing.append("hospital name")
        if missing:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": f"Medical bill is missing required fields: {', '.join(missing)}.",
            })

    if pharmacy is not None:
        missing = []
        if pharmacy.total_amount == 0:
            missing.append("total amount")
        if not pharmacy.medicines_purchased:
            missing.append("medicines purchased")
        if missing:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": f"Pharmacy bill is missing required fields: {', '.join(missing)}.",
            })

    if diagnostic is not None:
        missing = []
        if not diagnostic.tests_performed:
            missing.append("tests performed")
        if not diagnostic.report_date:
            missing.append("report date")
        if missing:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": f"Diagnostic report is missing required fields: {', '.join(missing)}.",
            })

    # ── Documentation: doctor registration format ─────────────────────────────
    # Only validate when a prescription was uploaded; an absent prescription is
    # already reported as MISSING_DOCUMENTS above.

    if rx is not None:
        reg = (rx.doctor_registration or "").strip()
        if not reg:
            hard_rejections.append({
                "code": "DOCTOR_REG_INVALID",
                "reason": "No doctor registration number present on the prescription.",
            })
        elif not _DOCTOR_REG_RE.match(reg):
            hard_rejections.append({
                "code": "DOCTOR_REG_INVALID",
                "reason": (
                    f"Doctor registration number '{reg}' does not match the required format "
                    "[StateCode]/[Number]/[Year] (e.g. KA/45678/2015)."
                ),
            })

    # ── Collect raw amounts ───────────────────────────────────────────────────

    consultation_fee = bill.consultation_fee if bill else 0.0
    procedure_charges = bill.procedure_charges if bill else 0.0
    other_charges = bill.other_charges if bill else 0.0
    bill_total = bill.total_amount if bill else 0.0
    pharmacy_total = pharmacy.total_amount if pharmacy else 0.0
    bill_date_str = (bill.bill_date or "") if bill else ""
    hospital_name = (bill.hospital_name or "") if bill else ""
    bill_number = (bill.bill_number or "") if bill else ""

    total_claimed = bill_total + pharmacy_total

    # ── Minimum claim amount ──────────────────────────────────────────────────

    min_amount = claim_reqs["minimum_claim_amount"]  # 500
    if 0 < total_claimed < min_amount:
        hard_rejections.append({
            "code": "BELOW_MIN_AMOUNT",
            "reason": f"Claim ₹{total_claimed:.0f} is below the minimum of ₹{min_amount}.",
        })

    # ── Consultation sub-limit + 10% copay ────────────────────────────────────

    consult_cfg = limits["consultation_fees"]
    consult_sub_limit = consult_cfg["sub_limit"]         # 2000
    consult_copay_pct = consult_cfg["copay_percentage"]  # 10

    if consultation_fee > 0:
        capped_consult = min(consultation_fee, consult_sub_limit)
        copay = round(capped_consult * consult_copay_pct / 100, 2)
        approved_consult = round(capped_consult - copay, 2)
        deductions["consultation_copay"] = copay
        amount_analysis["consultation"] = {
            "billed": consultation_fee,
            "sub_limit": consult_sub_limit,
            "capped_at": capped_consult,
            "copay_pct": consult_copay_pct,
            "copay_amount": copay,
            "approved": approved_consult,
        }
        if consultation_fee > consult_sub_limit:
            warnings.append({
                "code": "SUB_LIMIT_EXCEEDED",
                "reason": (
                    f"Consultation fee ₹{consultation_fee:.0f} exceeds sub-limit "
                    f"₹{consult_sub_limit}. Capped at ₹{consult_sub_limit}."
                ),
            })
    else:
        approved_consult = 0.0

    # ── Pharmacy sub-limit ────────────────────────────────────────────────────

    pharmacy_sub_limit = limits["pharmacy"]["sub_limit"]  # 15000
    if pharmacy_total > 0:
        capped_pharmacy = min(pharmacy_total, pharmacy_sub_limit)
        amount_analysis["pharmacy"] = {
            "billed": pharmacy_total,
            "sub_limit": pharmacy_sub_limit,
            "approved": capped_pharmacy,
        }
        if pharmacy_total > pharmacy_sub_limit:
            warnings.append({
                "code": "SUB_LIMIT_EXCEEDED",
                "reason": (
                    f"Pharmacy total ₹{pharmacy_total:.0f} exceeds sub-limit "
                    f"₹{pharmacy_sub_limit}. Capped at ₹{pharmacy_sub_limit}."
                ),
            })
    else:
        capped_pharmacy = 0.0

    # ── Diagnostic sub-limit ──────────────────────────────────────────────────

    diag_sub_limit = limits["diagnostic_tests"]["sub_limit"]  # 10000
    if other_charges > diag_sub_limit:
        warnings.append({
            "code": "SUB_LIMIT_EXCEEDED",
            "reason": (
                f"Other/diagnostic charges ₹{other_charges:.0f} exceed diagnostic "
                f"sub-limit ₹{diag_sub_limit}."
            ),
        })

    # ── Per-claim limit ───────────────────────────────────────────────────────

    per_claim_limit = limits["per_claim_limit"]  # 5000
    non_consult_bill = round(procedure_charges + other_charges, 2)
    subtotal = round(approved_consult + non_consult_bill + capped_pharmacy, 2)

    per_claim_exceeded = False
    if claimed_amount > 0 and claimed_amount > per_claim_limit:
        hard_rejections.append({
            "code": "PER_CLAIM_EXCEEDED",
            "reason": (
                f"Claimed amount ₹{claimed_amount:.0f} exceeds the per-claim limit "
                f"of ₹{per_claim_limit}."
            ),
        })
        per_claim_exceeded = True

    capped_subtotal = round(min(subtotal, per_claim_limit), 2)

    # ── Annual limit ──────────────────────────────────────────────────────────

    annual_limit = limits["annual_limit"]  # 50000
    annual_remaining = round(annual_limit - annual_spend, 2)

    if per_claim_exceeded:
        max_approvable = 0.0
    elif annual_spend >= annual_limit:
        hard_rejections.append({
            "code": "ANNUAL_LIMIT_EXCEEDED",
            "reason": (
                f"Annual limit of ₹{annual_limit:,.0f} has been fully exhausted "
                f"(₹{annual_spend:,.0f} already approved this policy year)."
            ),
        })
        max_approvable = 0.0
    else:
        if capped_subtotal > annual_remaining:
            warnings.append({
                "code": "ANNUAL_LIMIT_EXCEEDED",
                "reason": (
                    f"Claim ₹{capped_subtotal:.0f} would exceed annual remaining balance "
                    f"₹{annual_remaining:.0f}. Capped at remaining balance."
                ),
            })
        max_approvable = round(min(capped_subtotal, annual_remaining), 2)

    amount_analysis["total_claimed"] = total_claimed
    amount_analysis["per_claim_limit"] = per_claim_limit
    amount_analysis["annual_limit"] = annual_limit
    amount_analysis["annual_spend_to_date"] = annual_spend
    amount_analysis["annual_remaining"] = annual_remaining
    amount_analysis["max_approvable"] = max_approvable

    # ── Submission deadline (30 days) ─────────────────────────────────────────

    if bill_date_str:
        try:
            bill_date = datetime.strptime(bill_date_str, "%Y-%m-%d").date()
            days_elapsed = (today - bill_date).days
            deadline = claim_reqs["submission_timeline_days"]  # 30
            if days_elapsed > deadline:
                hard_rejections.append({
                    "code": "LATE_SUBMISSION",
                    "reason": (
                        f"Claim submitted {days_elapsed} days after treatment date "
                        f"({bill_date_str}). Deadline is {deadline} days."
                    ),
                })
            else:
                amount_analysis["submission_days_elapsed"] = days_elapsed
        except ValueError:
            pass

    # ── Waiting period checks ─────────────────────────────────────────────────

    if member_join_date:
        try:
            join_date = datetime.strptime(member_join_date, "%Y-%m-%d").date()
            treatment_date_str = (
                (rx.consultation_date if rx and rx.consultation_date else None)
                or bill_date_str
            )
            if treatment_date_str:
                try:
                    treatment_date = datetime.strptime(treatment_date_str, "%Y-%m-%d").date()
                    days_since_join = (treatment_date - join_date).days

                    initial_wait = policy["waiting_periods"]["initial_waiting"]  # 30
                    if days_since_join < initial_wait:
                        hard_rejections.append({
                            "code": "WAITING_PERIOD",
                            "reason": (
                                f"Treatment date {treatment_date_str} falls within the "
                                f"{initial_wait}-day initial waiting period "
                                f"(joined {member_join_date}, {days_since_join} days elapsed)."
                            ),
                        })

                    canonical = [c.lower() for c in (rx.canonical_conditions if rx else [])]
                    for condition, wait_days in policy["waiting_periods"]["specific_ailments"].items():
                        if condition.lower() in canonical:
                            satisfied = days_since_join >= wait_days
                            waiting_period_checks.append({
                                "condition": condition,
                                "required_days": wait_days,
                                "elapsed_days": days_since_join,
                                "status": "satisfied" if satisfied else "not_satisfied",
                            })
                            if not satisfied:
                                hard_rejections.append({
                                    "code": "WAITING_PERIOD",
                                    "reason": (
                                        f"Diagnosis includes '{condition}' which has a "
                                        f"{wait_days}-day waiting period. Only "
                                        f"{days_since_join} days have elapsed since policy start."
                                    ),
                                })
                except ValueError:
                    pass
        except ValueError:
            pass

    # ── Pre-authorization (MRI, CT Scan) ──────────────────────────────────────

    pre_auth_keywords = ["mri", "ct scan", "ct-scan"]
    all_tests: list[str] = []
    if diagnostic:
        all_tests += [t.lower() for t in diagnostic.tests_performed]
    if rx:
        all_tests += [t.lower() for t in rx.tests_advised]

    for test in all_tests:
        if any(kw in test for kw in pre_auth_keywords) and test not in pre_auth_flags:
            pre_auth_flags.append(test)
            warnings.append({
                "code": "PRE_AUTH_MISSING",
                "reason": f"'{test}' requires pre-authorization — verify if obtained.",
            })

    # ── Network hospital & cashless eligibility ───────────────────────────────

    network_status = None
    if hospital_name:
        is_network = any(n in hospital_name.lower() for n in network_hospitals)
        network_status = "network" if is_network else "non_network"
        if is_network:
            amount_analysis["network_discount_pct"] = consult_cfg["network_discount"]  # 20

    # ── Suggested decision ────────────────────────────────────────────────────
    # Copay is a standard cost-share — it does NOT make a claim partial. A claim
    # is partial only when amounts are capped by limits (sub-limit / per-claim /
    # annual). Incomplete treatment coverage (some items excluded) is the LLM's
    # call, so it may downgrade APPROVED -> PARTIAL, but never upgrade.
    limit_codes = {"SUB_LIMIT_EXCEEDED", "PER_CLAIM_EXCEEDED", "ANNUAL_LIMIT_EXCEEDED"}
    amount_capped_by_limits = any(w["code"] in limit_codes for w in warnings)

    if hard_rejections or max_approvable == 0:
        suggested_decision = "REJECTED"
    elif amount_capped_by_limits:
        suggested_decision = "PARTIAL"
    else:
        suggested_decision = "APPROVED"

    return {
        "hard_rejections": hard_rejections,
        "warnings": warnings,
        "deductions": deductions,
        "pre_auth_flags": pre_auth_flags,
        "waiting_period_checks": waiting_period_checks,
        "network_status": network_status,
        "amount_analysis": amount_analysis,
        "suggested_decision": suggested_decision,
    }


# ── Helper: extract a single document ────────────────────────────────────────

def extract_document(file_bytes: bytes, mime_type: str, prompt: str, schema_class):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return schema_class.model_validate_json(response.text)
    except Exception:
        return schema_class()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/members", response_model=MemberRecord)
def create_member(payload: MemberCreate):
    return db.create_member(
        member_id=payload.member_id,
        name=payload.name,
        join_date=payload.join_date,
        relationship=payload.relationship,
    )


@app.get("/members/{member_id}", response_model=MemberRecord)
def get_member(member_id: str):
    member = db.get_member(member_id)
    if not member:
        raise HTTPException(404, f"Member '{member_id}' not found.")
    return member



@app.post("/adjudicate-documents", response_model=DocumentAdjudicationResponse)
def adjudicate_documents(
    member_id: str = Form(...),
    member_join_date: str = Form(""),
    claimed_amount: float = Form(0),
    prescription: UploadFile | None = File(None),
    medical_bill: UploadFile | None = File(None),
    diagnostic_report: UploadFile | None = File(None),
    pharmacy_bill: UploadFile | None = File(None),
):
    if not prescription and not medical_bill:
        raise HTTPException(400, "At least a prescription or medical bill must be uploaded.")

    # ── DB checks (before extraction — fail fast on member issues) ────────────

    member = db.get_member(member_id)
    member_found = member is not None
    member_active = bool(member and member.get("is_active", False))

    # Use DB join_date if available; fall back to form value
    resolved_join_date = (
        member["join_date"] if member and member.get("join_date")
        else member_join_date
    )

    policy_year = date.today().year
    annual_spend = db.get_annual_spend(member_id, policy_year) if member_found else 0.0

    # ── Read file bytes upfront (UploadFile is not thread-safe) ──────────────

    def resolve_mime(f: UploadFile) -> str:
        ct = (f.content_type or "").lower()
        if ct and ct not in ("application/octet-stream", ""):
            return ct
        ext = Path(f.filename or "").suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
        }.get(ext, "image/jpeg")

    def read(f: UploadFile | None):
        if f is None:
            return None
        return f.file.read(), resolve_mime(f)

    files = {
        "prescription": read(prescription),
        "medical_bill": read(medical_bill),
        "diagnostic_report": read(diagnostic_report),
        "pharmacy_bill": read(pharmacy_bill),
    }

    agent_config = {
        "prescription": (PRESCRIPTION_PROMPT, ExtractedPrescription),
        "medical_bill": (MEDICAL_BILL_PROMPT, ExtractedMedicalBill),
        "diagnostic_report": (DIAGNOSTIC_PROMPT, ExtractedDiagnosticReport),
        "pharmacy_bill": (PHARMACY_BILL_PROMPT, ExtractedPharmacyBill),
    }

    # ── Run extraction agents in parallel ─────────────────────────────────────

    uploaded_files = {k: v for k, v in files.items() if v is not None}

    extractions: dict = {}
    with ThreadPoolExecutor() as pool:
        futures = {
            key: pool.submit(
                extract_document,
                file_bytes, mime_type,
                agent_config[key][0],
                agent_config[key][1],
            )
            for key, (file_bytes, mime_type) in uploaded_files.items()
        }
        for key, future in futures.items():
            extractions[key] = future.result()

    extraction_results = ExtractionResults(**extractions)

    # ── Duplicate check (needs extracted bill data) ───────────────────────────

    bill = extraction_results.medical_bill
    rx = extraction_results.prescription
    bill_number = (bill.bill_number or "") if bill else ""
    hospital_name = (bill.hospital_name or "") if bill else ""
    treatment_date_str = (
        (rx.consultation_date if rx and rx.consultation_date else None)
        or ((bill.bill_date or "") if bill else "")
    )

    is_duplicate = (
        member_found
        and db.check_duplicate(member_id, bill_number, treatment_date_str, hospital_name)
    )

    # ── Rule engine ───────────────────────────────────────────────────────────

    rule_findings = run_rule_engine(
        extractions=extraction_results,
        member_join_date=resolved_join_date,
        member_found=member_found,
        member_active=member_active,
        annual_spend=annual_spend,
        is_duplicate=is_duplicate,
        claimed_amount=claimed_amount,
    )

    # ── Adjudication LLM call ─────────────────────────────────────────────────

    # Query Neo4j for only the policy nodes relevant to this claim
    policy_context = graph_store.query_relevant_policy(extraction_results)
    system_prompt = _build_system_prompt(policy_context)

    claim_id = f"CLM_{int(time.time() * 1000) % 100000:05d}"
    adjudication_input = {
        "claim_id": claim_id,
        "member_id": member_id,
        "member_join_date": resolved_join_date or None,
        "member_claimed_amount": claimed_amount or None,
        "extracted_documents": extraction_results.model_dump(exclude_none=True),
        "rule_engine_findings": rule_findings,
    }

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                "Adjudicate this OPD claim. The rule_engine_findings contain all deterministic "
                "checks already evaluated. Your role is to assess document validity, medical "
                "necessity, coverage, and fraud — then produce the final decision.\n\n"
                f"```json\n{json.dumps(adjudication_input, indent=2)}\n```"
            ),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0,
            ),
        )
        decision = AdjudicationDecision.model_validate_json(response.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── Persist claim and documents ───────────────────────────────────────────

    if member_found:
        db.save_claim(
            claim_id=claim_id,
            member_id=member_id,
            decision=decision.decision,
            approved_amount=decision.approved_amount,
            total_claimed=rule_findings["amount_analysis"].get("total_claimed", 0),
            treatment_date=treatment_date_str,
            bill_number=bill_number,
            hospital_name=hospital_name,
            policy_year=policy_year,
        )
        db.save_claim_documents(
            claim_id=claim_id,
            documents=extraction_results.model_dump(exclude_none=True),
        )

    return DocumentAdjudicationResponse(
        extractions=extraction_results,
        decision=decision,
        policy_context=policy_context,
    )
