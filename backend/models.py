from pydantic import BaseModel, model_validator
from typing import Literal, Optional

class ExtractedPrescription(BaseModel):
    doctor_name: str = ""
    doctor_registration: str = ""
    patient_name: str = ""
    consultation_date: str = ""
    diagnosis: str = ""
    canonical_conditions: list[str] = []
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
    line_items: list[str] = []
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
    medicines_purchased: list[str] = []
    total_amount: float = 0


class ExtractionResults(BaseModel):
    prescription: Optional[ExtractedPrescription] = None
    medical_bill: Optional[ExtractedMedicalBill] = None
    diagnostic_report: Optional[ExtractedDiagnosticReport] = None
    pharmacy_bill: Optional[ExtractedPharmacyBill] = None


# Adjudication Decision Output

class AdjudicationDecision(BaseModel):
    claim_id: str
    decision: Literal["APPROVED", "REJECTED", "PARTIAL", "MANUAL_REVIEW"]
    approved_amount: float
    rejection_reasons: list[str] = []
    confidence_score: float
    notes: str = ""
    next_steps: str = ""

    @model_validator(mode="after")
    def clear_rejection_reasons_for_non_rejected(self):
        if self.decision != "REJECTED":
            self.rejection_reasons = []
        return self


# Specialist agent findings (LangGraph multi-agent layer)

class CoverageFinding(BaseModel):
    item: str
    status: Literal["covered", "excluded", "uncertain"]
    reason: str = ""


class CoverageReport(BaseModel):
    findings: list[CoverageFinding] = []
    # Best estimate of the rupee value attributable to the EXCLUDED items
    # (including the consultation/tests/medicines that ride on an excluded
    # treatment). 0 when nothing is excluded. Used to compute partial amounts.
    excluded_amount: float = 0.0
    summary: str = ""


class NecessityFinding(BaseModel):
    item: str
    necessity: Literal["necessary", "not_necessary", "uncertain"]
    reason: str = ""


class NecessityReport(BaseModel):
    findings: list[NecessityFinding] = []
    summary: str = ""


class ValidityFinding(BaseModel):
    issue: str
    severity: Literal["low", "medium", "high"]
    detail: str = ""


class ValidityReport(BaseModel):
    documents_consistent: bool = True
    findings: list[ValidityFinding] = []
    summary: str = ""


class FraudFinding(BaseModel):
    indicator: str
    severity: Literal["low", "medium", "high"]
    detail: str = ""


class FraudReport(BaseModel):
    suspicion_level: Literal["none", "low", "medium", "high"] = "none"
    findings: list[FraudFinding] = []
    summary: str = ""


class DocumentAdjudicationResponse(BaseModel):
    extractions: ExtractionResults
    decision: AdjudicationDecision
    policy_context: dict = {}
    agent_reports: dict = {}


# Member Records

class MemberCreate(BaseModel):
    member_id: str
    name: str
    join_date: str
    relationship: str = "employee"


class MemberRecord(BaseModel):
    member_id: str
    name: str
    join_date: str
    is_active: bool
    relationship: str