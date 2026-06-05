import random
import time

from google import genai
from google.genai import types
from models import ExtractedPrescription, ExtractedMedicalBill, ExtractedDiagnosticReport, ExtractedPharmacyBill

MAX_RETRIES = 5          # total attempts per extraction call
BASE_DELAY = 1.0         # seconds; doubles each retry


def _is_retryable(exc: Exception) -> bool:
    """Rate limits (429) and transient server errors (5xx) are worth retrying."""
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    msg = str(exc).lower()
    return any(
        kw in msg
        for kw in ("rate limit", "429", "resource_exhausted", "quota",
                   "unavailable", "503", "overloaded", "deadline")
    )

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

agent_config = {
    "prescription": (PRESCRIPTION_PROMPT, ExtractedPrescription),
    "medical_bill": (MEDICAL_BILL_PROMPT, ExtractedMedicalBill),
    "diagnostic_report": (DIAGNOSTIC_PROMPT, ExtractedDiagnosticReport),
    "pharmacy_bill": (PHARMACY_BILL_PROMPT, ExtractedPharmacyBill),
}

def extract_document(client: genai.Client, file_bytes: bytes, mime_type: str, prompt: str, schema_class):
    """
    Extract a document into its schema. Retries with exponential backoff + jitter
    on rate limits / transient server errors so a throttled call doesn't get
    mistaken for an illegible document. Returns an empty model only after all
    retries are exhausted (or on a non-retryable error).
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            return schema_class.model_validate_json(response.text)
        except Exception as exc:
            if _is_retryable(exc) and attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
                continue
            return schema_class()