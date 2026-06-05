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

import database as db
import graph_store
from models import (
    DocumentAdjudicationResponse,
    ExtractedDiagnosticReport,
    ExtractedMedicalBill,
    ExtractedPharmacyBill,
    ExtractedPrescription,
    ExtractionResults,
    MemberCreate,
    MemberRecord,
)
from rule_engine import run_rule_engine
from document_extractor import extract_document, agent_config
from adjudication_graph import run_adjudication

load_dotenv()

app = FastAPI(title="OPD Adjudication API", version="2.0.0")

# Comma-separated list of allowed frontend origins; localhost stays available for dev.
_frontend_origins = [
    o.strip()
    for o in os.environ.get("FRONTEND_URLS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

ROOT = Path(__file__).parent.parent
_policy = (ROOT / "policy_terms.json").read_text()
_policy_data: dict = json.loads(_policy)


@app.on_event("startup")
def startup():
    db.init_db()
    graph_store.init_graph(_policy_data)


# Endpoints

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

    # Database checks

    member = db.get_member(member_id)
    member_found = member is not None
    member_active = bool(member and member.get("is_active", False))

    resolved_join_date = (
        member["join_date"] if member and member.get("join_date")
        else member_join_date
    )

    policy_year = date.today().year
    annual_spend = db.get_annual_spend(member_id, policy_year) if member_found else 0.0

    # Read files

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

    # Run extraction agents in parallel

    uploaded_files = {k: v for k, v in files.items() if v is not None}

    extractions: dict = {}
    with ThreadPoolExecutor() as pool:
        futures = {
            key: pool.submit(
                extract_document,
                client,
                file_bytes, mime_type,
                agent_config[key][0],
                agent_config[key][1],
            )
            for key, (file_bytes, mime_type) in uploaded_files.items()
        }
        for key, future in futures.items():
            extractions[key] = future.result()

    extraction_results = ExtractionResults(**extractions)

    # Duplicate file check

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

    # Running rule engine

    rule_findings = run_rule_engine(
        extractions=extraction_results,
        member_join_date=resolved_join_date,
        member_found=member_found,
        member_active=member_active,
        annual_spend=annual_spend,
        is_duplicate=is_duplicate,
        claimed_amount=claimed_amount,
    )

    # Adjudication via multi-agent LangGraph (coverage / necessity / validity /
    # fraud specialists run in parallel, then a synthesis node merges them with
    # the deterministic rule-engine findings).

    # Query Neo4j for only the policy nodes relevant to this claim
    policy_context = graph_store.query_relevant_policy(extraction_results)

    claim_id = f"CLM_{int(time.time() * 1000) % 100000:05d}"
    try:
        decision, agent_reports = run_adjudication(
            claim_id=claim_id,
            extracted_documents=extraction_results.model_dump(exclude_none=True),
            policy_context=policy_context,
            rule_findings=rule_findings,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Save claims and documents

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
        agent_reports=agent_reports,
    )
