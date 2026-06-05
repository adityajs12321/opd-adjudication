import json
import os
import random
import time
from pathlib import Path
from typing import Optional, TypedDict

from google import genai
from google.genai import types
from langgraph.graph import StateGraph, START, END

from models import (
    AdjudicationDecision,
    CoverageReport,
    FraudReport,
    NecessityReport,
    ValidityReport,
)

MODEL = "gemini-2.5-flash"
MAX_RETRIES = 5
BASE_DELAY = 1.0

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


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

ROOT = Path(__file__).parent.parent
_rules_data: dict = json.loads((ROOT / "adjudication_rules.json").read_text())
_fraud_indicators = _rules_data.get("fraud_indicators", [])
_priority_order = _rules_data.get("priority_order", [])


# ── Gemini helper ─────────────────────────────────────────────────────────────

def _call(system_prompt: str, payload: dict, schema_class):
    """
    Call Gemini with a scoped system prompt + JSON payload, parse into a model.
    Retries with exponential backoff + jitter on rate limits / transient errors.
    """
    contents = f"```json\n{json.dumps(payload, indent=2, default=str)}\n```"
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        temperature=0,
    )

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
            text = getattr(resp, "text", None)
            if not text:
                return None
            return schema_class.model_validate_json(text)
        except Exception as exc:
            # Retry only transient failures, and never after the last attempt.
            if attempt < MAX_RETRIES - 1 and _is_retryable(exc):
                delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
                continue
            return None
    return None


# ── Shared state ──────────────────────────────────────────────────────────────

class AdjudicationState(TypedDict, total=False):
    # inputs
    claim_id: str
    extracted_documents: dict
    policy_context: dict
    rule_findings: dict
    # specialist outputs
    coverage: dict
    necessity: dict
    validity: dict
    fraud: dict
    # final
    decision: dict


# ── Specialist agent prompts ──────────────────────────────────────────────────

COVERAGE_PROMPT = """You are a coverage specialist for OPD insurance. The goal
is to approve claims that fall under the policy, not to find reasons to deny them.

Given the extracted claim documents, the covered policy categories, and the exclusions list,
decide for the claim's treatment whether it is covered.

Guidelines:
- General OPD care — consultations, common tests, prescribed medicines, standard procedures —
  is COVERED by default. You do NOT need an itemized cost breakdown to mark something covered.
- Mark an item "excluded" ONLY when it clearly and directly matches a listed exclusion.
- Do not mark things "uncertain" for missing prices, missing line items, or minor documentation
  gaps. Coverage is about the type of treatment, not how it was billed.
- Exclusions override everything. A consultation, test, or medicine is only covered if the
  underlying treatment/condition it is for is itself covered. If the base treatment is excluded,
  its consultation fee, related tests, and related medicines are ALSO excluded — mark them
  "excluded" too, with a reason that ties them back to the excluded treatment.

Category cues (map the treatment to the right policy bucket before deciding):
- Dental: fillings, extractions, root canal, cleaning are COVERED. Teeth whitening / veneers and
  other cosmetic dentistry are EXCLUDED (cosmetic procedures).
- Alternative medicine: Ayurveda, Homeopathy, Unani are COVERED — this includes Ayurvedic therapies
  like Panchakarma. Other non-allopathic systems (e.g. Naturopathy, Siddha) are EXCLUDED.
- Vision: eye tests, glasses, contact lenses are COVERED; LASIK is EXCLUDED.
- EXCLUDED regardless of diagnosis: cosmetic procedures; weight-loss / bariatric treatment & diet
  plans; infertility treatment; experimental treatments; self-inflicted or adventure-sport injuries;
  HIV/AIDS; alcohol/drug-abuse treatment; vitamins/supplements unless prescribed for a deficiency.

Return JSON:
{
  "findings": [{"item": "treatment/service/category", "status": "covered|excluded|uncertain", "reason": "short justification"}],
  "excluded_amount": 0.0,
  "summary": "one-line overall coverage assessment"
}
For excluded_amount, estimate the total rupee value of the EXCLUDED items using the amounts in the
bill/line_items — and include the consultation fee, tests, and medicines that ride on an excluded
treatment. Use 0.0 when nothing is excluded. If everything is excluded, set it to the full bill.
If the overall treatment is covered, say so plainly in the summary."""

NECESSITY_PROMPT = """You are a medical necessity specialist for OPD insurance.

Given the prescription (diagnosis, conditions, medicines, tests, procedures) and any diagnostic
report, assess whether the treatment is medically reasonable for the diagnosis.

Guidelines:
- Treatment that plausibly relates to the diagnosis is "necessary" by default.
- Mark an item "not_necessary" ONLY when it is clearly unrelated to the diagnosis or obviously
  inappropriate. A missing or terse diagnosis is NOT grounds to question necessity.
- Do not require itemized costs, exhaustive notes, or perfect documentation.

Return JSON:
{
  "findings": [{"item": "test/medicine/procedure", "necessity": "necessary|not_necessary|uncertain", "reason": "short justification"}],
  "summary": "one-line overall necessity assessment"
}"""

VALIDITY_PROMPT = """You are a document validation specialist for OPD insurance.
Given all extracted documents and the claim requirements, check:
- Doctor registration present and formatted as [StateCode]/[Number]/[Year]
- Patient name consistent across all documents
- Treatment/bill/report dates consistent with each other
- Required fields present and legible
- Any sign of tampering or internal inconsistency

Return JSON:
{
  "documents_consistent": true|false,
  "findings": [{"issue": "short issue label", "severity": "low|medium|high", "detail": "what is wrong and in which document"}],
  "summary": "one-line overall validity assessment"
}
Only report actual problems in findings. If everything checks out, return an empty findings array and documents_consistent=true."""

FRAUD_PROMPT = """You are a fraud detection specialist for OPD insurance.
Given all extracted documents, the rule-engine findings (amounts, network status), and the list of
known fraud indicators, identify any matching suspicious patterns.

Return JSON:
{
  "suspicion_level": "none|low|medium|high",
  "findings": [{"indicator": "which fraud indicator matched", "severity": "low|medium|high", "detail": "evidence from the documents"}],
  "summary": "one-line overall fraud assessment"
}
Only flag indicators with concrete supporting evidence. Default to suspicion_level=none when nothing matches."""

SYNTHESIS_PROMPT = """You are the chief adjudicator for OPD insurance. You receive:
- `rule_engine_findings`: deterministic results (hard_rejections, max_approvable, deductions, suggested_decision)
- four specialist reports: coverage, necessity, validity, fraud

Produce the FINAL decision by combining them. Default to APPROVAL — lean toward approving any
claim whose treatment is covered.

DECISION RUBRIC (decide by how many items are covered):
- APPROVED  → ALL treatments/items are covered and medically reasonable (no hard_rejections).
- PARTIAL   → MIXED: at least one item is covered AND at least one item is excluded or clearly
              not medically necessary. This is the common case — approve the covered portion and
              list the dropped items. A single excluded item among several covered ones is
              PARTIAL, **never** REJECTED.
- REJECTED  → ONLY when there is a hard_rejection, OR every item is excluded / not covered (i.e.
              nothing is approvable). Do not REJECT a claim that has any covered, approvable item.
              Note: a consultation fee is NOT a standalone approvable item — if the only treatment
              is excluded, the consultation for it is excluded too, so the claim is REJECTED.
- MANUAL_REVIEW → HIGH-severity fraud/validity findings, or genuinely ambiguous cases.

PRE-AUTHORIZATION: MRI and CT scans require pre-authorization. If rule_engine_findings.pre_auth_flags
is non-empty (or a PRE_AUTH_MISSING warning is present) and there is no evidence pre-auth was obtained,
REJECT the claim with code PRE_AUTH_MISSING.

approved_amount:
- You do NOT compute the final figure — it is recomputed deterministically from max_approvable and
  the coverage report's excluded_amount. Just echo your best estimate; it will be clamped/overridden.
- The excluded_amount in the coverage report drives partial deductions. When a treatment is excluded,
  its consultation fee, tests, and medicines are excluded with it — they ride on the base treatment's
  coverage and cannot be approved on their own.
- For APPROVED, approve the full max_approvable. Do not whittle it down over missing line items.

REJECTION CODES — when decision is REJECTED, populate rejection_reasons with the applicable codes:
- Always include EVERY code from rule_engine_findings.hard_rejections.
- Add judgment-based codes the rule engine cannot detect:
  - SERVICE_NOT_COVERED → the treatment is excluded by the policy (cosmetic, weight-loss, etc.).
  - PRE_AUTH_MISSING    → MRI/CT performed without pre-authorization (see above).
  - NOT_MEDICALLY_NECESSARY → treatment clearly unrelated to the diagnosis.

Other rules:
- Include EVERY code from rule_engine_findings.hard_rejections when decision is REJECTED.
- Copay is a normal cost-share — copay alone does NOT make a claim PARTIAL.
- Minor/incomplete documentation is NOT a reason to reduce or downgrade — ignore
  INCOMPLETE_DOCUMENTATION warnings. Low/medium validity or fraud notes do not block a claim.
- You may DOWNGRADE rule_engine_findings.suggested_decision but never UPGRADE it.
- When specialist reports conflict, follow this priority order: {priority}.

Return JSON:
{{
  "claim_id": "string (echo the input claim_id)",
  "decision": "APPROVED|REJECTED|PARTIAL|MANUAL_REVIEW",
  "approved_amount": number,
  "rejection_reasons": ["codes — only when decision is REJECTED, else empty"],
  "confidence_score": number 0.0-1.0,
  "notes": "key observations from the specialist reports",
  "next_steps": "what the claimant should do"
}}""".replace("{priority}", json.dumps(_priority_order))


# ── Nodes ─────────────────────────────────────────────────────────────────────

def coverage_node(state: AdjudicationState) -> dict:
    payload = {
        "extracted_documents": state["extracted_documents"],
        "covered_categories": state["policy_context"].get("coverage", {}),
        "exclusions": state["policy_context"].get("exclusions", []),
    }
    report = _call(COVERAGE_PROMPT, payload, CoverageReport) or CoverageReport()
    return {"coverage": report.model_dump()}


def necessity_node(state: AdjudicationState) -> dict:
    docs = state["extracted_documents"]
    payload = {
        "prescription": docs.get("prescription"),
        "diagnostic_report": docs.get("diagnostic_report"),
        "pharmacy_bill": docs.get("pharmacy_bill"),
        "covered_categories": list(state["policy_context"].get("coverage", {}).keys()),
    }
    report = _call(NECESSITY_PROMPT, payload, NecessityReport) or NecessityReport()
    return {"necessity": report.model_dump()}


def validity_node(state: AdjudicationState) -> dict:
    payload = {
        "extracted_documents": state["extracted_documents"],
        "claim_requirements": state["policy_context"].get("claim_requirements", {}),
    }
    report = _call(VALIDITY_PROMPT, payload, ValidityReport) or ValidityReport()
    return {"validity": report.model_dump()}


def fraud_node(state: AdjudicationState) -> dict:
    rf = state["rule_findings"]
    payload = {
        "extracted_documents": state["extracted_documents"],
        "network_status": rf.get("network_status"),
        "amount_analysis": rf.get("amount_analysis", {}),
        "known_fraud_indicators": _fraud_indicators,
    }
    report = _call(FRAUD_PROMPT, payload, FraudReport) or FraudReport()
    return {"fraud": report.model_dump()}


def synthesis_node(state: AdjudicationState) -> dict:
    rf = state["rule_findings"]
    payload = {
        "claim_id": state["claim_id"],
        "rule_engine_findings": rf,
        "coverage_report": state.get("coverage", {}),
        "necessity_report": state.get("necessity", {}),
        "validity_report": state.get("validity", {}),
        "fraud_report": state.get("fraud", {}),
    }
    decision: Optional[AdjudicationDecision] = _call(SYNTHESIS_PROMPT, payload, AdjudicationDecision)

    if decision is None:
        # Fail safe: never auto-approve on a synthesis failure
        decision = AdjudicationDecision(
            claim_id=state["claim_id"],
            decision="MANUAL_REVIEW",
            approved_amount=0.0,
            confidence_score=0.0,
            notes="Synthesis agent failed to produce a decision; routed to manual review.",
            next_steps="A human adjudicator should review this claim.",
        )

    # ── Enforce deterministic constraints the LLM must not violate ────────────
    # The LLM decides the verdict (covered / excluded / partial); the rupee
    # figure is computed here, NOT taken from the LLM, so it can never approve
    # more than the policy allows.
    max_approvable = rf.get("amount_analysis", {}).get("max_approvable", 0.0)

    hard_codes = [r["code"] for r in rf.get("hard_rejections", [])]
    if hard_codes and decision.decision != "REJECTED":
        # Deterministic hard rejections override a softer LLM verdict
        decision.decision = "REJECTED"

    # Value of the excluded portion as estimated by the coverage agent, clamped
    # to the approvable range.
    coverage = state.get("coverage", {})
    excluded_amount = float(coverage.get("excluded_amount", 0.0) or 0.0)
    excluded_amount = max(0.0, min(excluded_amount, max_approvable))

    if decision.decision == "APPROVED":
        decision.approved_amount = max_approvable
    elif decision.decision == "PARTIAL":
        decision.approved_amount = round(max(0.0, max_approvable - excluded_amount), 2)
        # Nothing left to approve after dropping excluded items → it's a rejection.
        if decision.approved_amount == 0.0:
            decision.decision = "REJECTED"
    else:  # REJECTED, MANUAL_REVIEW
        decision.approved_amount = 0.0

    if decision.decision == "REJECTED":
        decision.rejection_reasons = list(
            dict.fromkeys(hard_codes + decision.rejection_reasons)
        )

    return {"decision": decision.model_dump()}


# ── Graph assembly ────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(AdjudicationState)
    g.add_node("coverage", coverage_node)
    g.add_node("necessity", necessity_node)
    g.add_node("validity", validity_node)
    g.add_node("fraud", fraud_node)
    g.add_node("synthesis", synthesis_node)

    # Fan out from START to the four specialists (run in parallel), then converge.
    for specialist in ("coverage", "necessity", "validity", "fraud"):
        g.add_edge(START, specialist)
        g.add_edge(specialist, "synthesis")
    g.add_edge("synthesis", END)

    return g.compile()


_graph = _build_graph()


def run_adjudication(
    claim_id: str,
    extracted_documents: dict,
    policy_context: dict,
    rule_findings: dict,
) -> tuple[AdjudicationDecision, dict]:
    """Run the multi-agent graph. Returns (decision, agent_reports)."""
    final = _graph.invoke({
        "claim_id": claim_id,
        "extracted_documents": extracted_documents,
        "policy_context": policy_context,
        "rule_findings": rule_findings,
    })

    decision = AdjudicationDecision.model_validate(final["decision"])
    agent_reports = {
        "coverage": final.get("coverage", {}),
        "necessity": final.get("necessity", {}),
        "validity": final.get("validity", {}),
        "fraud": final.get("fraud", {}),
    }
    return decision, agent_reports
