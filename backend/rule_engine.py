from models import ExtractionResults
from datetime import datetime, date
import re
from pathlib import Path
import json

ROOT = Path(__file__).parent.parent
# Default policy loaded from disk; overridden at startup with the active policy
# from Neo4j (the source of truth) via set_policy().
_policy = (ROOT / "policy_terms.json").read_text()
_policy_data: dict = json.loads(_policy)


def set_policy(policy_data: dict):
    """Replace the in-memory policy used for deterministic rule checks."""
    global _policy_data
    _policy_data = policy_data


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

    # Collect uploaded documents

    bill = extractions.medical_bill
    rx = extractions.prescription
    pharmacy = extractions.pharmacy_bill
    diagnostic = extractions.diagnostic_report

    # Eligibility

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

    # Documentation: missing documents

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

    # Documentation: legibility vs completeness
    #
    # Two distinct signals — do NOT conflate them:
    #   ILLEGIBLE_DOCUMENTS      → extraction returned essentially nothing, meaning the
    #                              scan was unreadable / the wrong file / corrupt.
    #   INCOMPLETE_DOCUMENTATION → the document was read fine but a specific field is
    #                              absent. A legible bill is NOT illegible just because
    #                              one field didn't populate.

    if rx is not None:
        rx_has_content = bool(
            rx.doctor_name or rx.diagnosis or rx.canonical_conditions
            or rx.medicines_prescribed or rx.tests_advised or rx.procedures
        )
        if not rx_has_content:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": "Prescription could not be read — no information was extractable. The scan may be illegible or the wrong file.",
            })
        else:
            missing = []
            if not rx.diagnosis and not rx.canonical_conditions:
                missing.append("diagnosis")
            if not rx.medicines_prescribed and not rx.tests_advised and not rx.procedures:
                missing.append("medicines, tests, or procedures")
            if missing:
                warnings.append({
                    "code": "INCOMPLETE_DOCUMENTATION",
                    "reason": f"Prescription is readable but missing: {', '.join(missing)}.",
                })

    if bill is not None:
        # An amount counts if it appears in the total OR any itemised component.
        bill_amount = bill.total_amount or (
            bill.consultation_fee + bill.procedure_charges + bill.other_charges
        )
        bill_has_content = bool(
            bill_amount or bill.hospital_name or bill.patient_name
            or bill.bill_number or bill.line_items
        )
        if not bill_has_content:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": "Medical bill could not be read — no information was extractable. The scan may be illegible or the wrong file.",
            })
        else:
            missing = []
            if not bill_amount:
                missing.append("amount")
            if not bill.bill_date:
                missing.append("bill date")
            if not bill.hospital_name:
                missing.append("hospital name")
            if missing:
                warnings.append({
                    "code": "INCOMPLETE_DOCUMENTATION",
                    "reason": f"Medical bill is readable but missing: {', '.join(missing)}.",
                })

    if pharmacy is not None:
        pharmacy_has_content = bool(
            pharmacy.total_amount or pharmacy.medicines_purchased
            or pharmacy.pharmacy_name
        )
        if not pharmacy_has_content:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": "Pharmacy bill could not be read — no information was extractable. The scan may be illegible or the wrong file.",
            })
        else:
            missing = []
            if not pharmacy.total_amount:
                missing.append("total amount")
            if not pharmacy.medicines_purchased:
                missing.append("medicines purchased")
            if missing:
                warnings.append({
                    "code": "INCOMPLETE_DOCUMENTATION",
                    "reason": f"Pharmacy bill is readable but missing: {', '.join(missing)}.",
                })

    if diagnostic is not None:
        diagnostic_has_content = bool(
            diagnostic.tests_performed or diagnostic.lab_name or diagnostic.summary
        )
        if not diagnostic_has_content:
            warnings.append({
                "code": "ILLEGIBLE_DOCUMENTS",
                "reason": "Diagnostic report could not be read — no information was extractable. The scan may be illegible or the wrong file.",
            })
        else:
            missing = []
            if not diagnostic.tests_performed:
                missing.append("tests performed")
            if not diagnostic.report_date:
                missing.append("report date")
            if missing:
                warnings.append({
                    "code": "INCOMPLETE_DOCUMENTATION",
                    "reason": f"Diagnostic report is readable but missing: {', '.join(missing)}.",
                })

    # Documentation: invalid documents
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

    # Collect raw amounts

    consultation_fee = bill.consultation_fee if bill else 0.0
    procedure_charges = bill.procedure_charges if bill else 0.0
    other_charges = bill.other_charges if bill else 0.0
    bill_total = bill.total_amount if bill else 0.0
    pharmacy_total = pharmacy.total_amount if pharmacy else 0.0
    bill_date_str = (bill.bill_date or "") if bill else ""
    hospital_name = (bill.hospital_name or "") if bill else ""
    bill_number = (bill.bill_number or "") if bill else ""

    # Robust "actually billed" figure: trust the printed total, but fall back to
    # the sum of components if the total field didn't extract.
    bill_billed = bill_total or round(consultation_fee + procedure_charges + other_charges, 2)
    total_claimed = round(bill_billed + pharmacy_total, 2)

    # Min claim amount

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

    # Hard ceiling: never approve more than was actually billed. Guards against
    # per-line components being double-counted (or mis-extracted into several
    # fields) and inflating the subtotal above the real bill total.
    if total_claimed > 0:
        max_approvable = round(min(max_approvable, total_claimed), 2)

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