from pydantic import BaseModel
from typing import Literal, Optional


# ── Extraction models (one per document type) ────────────────────────────────

class ExtractedPrescription(BaseModel):
    doctor_name: str = ""
    doctor_registration: str = ""
    patient_name: str = ""
    consultation_date: str = ""
    diagnosis: str = ""
    medicines_prescribed: list[str] = []
    tests_advised: list[str] = []
    procedures: list[str] = []
    notes: str = ""


class ExtractedMedicalBill(BaseModel):
    hospital_name: str = ""
    bill_number: str = ""
    bill_date: str = ""
    patient_name: str = ""
    consultation_fee: float = 0
    procedure_charges: float = 0
    other_charges: float = 0
    total_amount: float = 0
    line_items: list[str] = []   # e.g. ["Consultation: ₹1000", "X-Ray: ₹500"]
    payment_mode: str = ""


class ExtractedDiagnosticReport(BaseModel):
    lab_name: str = ""
    accreditation: str = ""
    report_date: str = ""
    patient_name: str = ""
    tests_performed: list[str] = []
    abnormal_findings: list[str] = []
    pathologist: str = ""
    summary: str = ""


class ExtractedPharmacyBill(BaseModel):
    pharmacy_name: str = ""
    drug_license: str = ""
    bill_date: str = ""
    patient_name: str = ""
    doctor_name: str = ""
    medicines_purchased: list[str] = []   # e.g. ["Paracetamol 500mg x10 - ₹50"]
    total_amount: float = 0


class ExtractionResults(BaseModel):
    prescription: Optional[ExtractedPrescription] = None
    medical_bill: Optional[ExtractedMedicalBill] = None
    diagnostic_report: Optional[ExtractedDiagnosticReport] = None
    pharmacy_bill: Optional[ExtractedPharmacyBill] = None


# ── Adjudication decision ────────────────────────────────────────────────────

class AdjudicationDecision(BaseModel):
    claim_id: str
    decision: Literal["APPROVED", "REJECTED", "PARTIAL", "MANUAL_REVIEW"]
    approved_amount: float
    rejection_reasons: list[str] = []
    confidence_score: float
    notes: str = ""
    next_steps: str = ""
    reasoning: str = ""
    cashless_approved: Optional[bool] = None
    network_discount: Optional[float] = None
    deductions: Optional[dict[str, float]] = None
    rejected_items: Optional[list[str]] = None
    flags: Optional[list[str]] = None


class DocumentAdjudicationResponse(BaseModel):
    extractions: ExtractionResults
    decision: AdjudicationDecision


# ── Member models ─────────────────────────────────────────────────────────────

class MemberCreate(BaseModel):
    member_id: str
    name: str
    join_date: str                          # YYYY-MM-DD
    relationship: str = "employee"


class MemberRecord(BaseModel):
    member_id: str
    name: str
    join_date: str
    is_active: bool
    relationship: str


