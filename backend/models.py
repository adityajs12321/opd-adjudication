from pydantic import BaseModel
from typing import Literal, Optional


class Prescription(BaseModel):
    doctor_name: Optional[str] = None
    doctor_reg: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines_prescribed: Optional[list[str]] = None
    treatment: Optional[str] = None
    tests_prescribed: Optional[list[str]] = None
    procedures: Optional[list[str]] = None


class Bill(BaseModel):
    consultation_fee: Optional[float] = None
    medicines: Optional[float] = None
    diagnostic_tests: Optional[float] = None
    test_names: Optional[list[str]] = None


class ClaimDocuments(BaseModel):
    prescription: Optional[Prescription] = None
    bill: Optional[Bill] = None


class ClaimRequest(BaseModel):
    member_id: str
    member_name: str
    member_join_date: Optional[str] = None
    treatment_date: str
    claim_amount: float
    hospital: Optional[str] = None
    cashless_request: Optional[bool] = None
    previous_claims_same_day: Optional[int] = None
    documents: ClaimDocuments


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
