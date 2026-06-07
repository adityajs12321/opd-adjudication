# API Documentation

Base URL (local): `http://localhost:8000`

All responses are JSON. CORS allowed origins are controlled by the `FRONTEND_URLS` env var
(comma-separated; defaults to `http://localhost:3000`). Allowed methods: `GET`, `POST`, `PUT`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness check |
| `POST` | `/members` | Create / upsert a member |
| `GET`  | `/members/{member_id}` | Fetch a member |
| `POST` | `/adjudicate-documents` | Adjudicate uploaded claim documents |
| `GET`  | `/policy` | Fetch the active policy |
| `PUT`  | `/policy` | Replace the active policy (validate + persist + rebuild) |

---

## `GET /health`

Liveness probe.

**Response `200`**
```json
{ "status": "ok" }
```

---

## `POST /members`

Creates a member, or updates one if `member_id` already exists (upsert). A claim can only be
adjudicated for a member that exists here.

**Request body** (`application/json`)

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `member_id` | string | yes | — | Primary key |
| `name` | string | yes | — | |
| `join_date` | string | yes | — | `YYYY-MM-DD`; drives waiting-period checks |
| `relationship` | string | no | `"employee"` | e.g. `employee`, `spouse`, `child` |

```json
{
  "member_id": "EMP001",
  "name": "Rajesh Kumar",
  "join_date": "2024-01-15",
  "relationship": "employee"
}
```

**Response `200`** — `MemberRecord`
```json
{
  "member_id": "EMP001",
  "name": "Rajesh Kumar",
  "join_date": "2024-01-15",
  "is_active": true,
  "relationship": "employee"
}
```

**Example**
```bash
curl -X POST http://localhost:8000/members \
  -H "Content-Type: application/json" \
  -d '{"member_id":"EMP001","name":"Rajesh Kumar","join_date":"2024-01-15"}'
```

---

## `GET /members/{member_id}`

**Response `200`** — `MemberRecord` (see above).

**Response `404`** — member not found:
```json
{ "detail": "Member 'EMP999' not found." }
```

---

## `POST /adjudicate-documents`

Extracts, evaluates, and adjudicates a claim from its uploaded documents. This is a
**`multipart/form-data`** request (it carries file uploads).

At least a `prescription` **or** a `medical_bill` must be provided, otherwise `400`.

### Form fields

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `member_id` | text | yes | — | Must match a member created via `/members` |
| `member_join_date` | text | no | `""` | `YYYY-MM-DD`; fallback if the member's stored join date is absent |
| `claimed_amount` | number | no | `0` | Claimant-stated total; used for the per-claim limit check |
| `prescription` | file | conditional | — | Image or PDF |
| `medical_bill` | file | conditional | — | Image or PDF |
| `diagnostic_report` | file | no | — | Image or PDF |
| `pharmacy_bill` | file | no | — | Image or PDF |

Supported file types: PDF and common images (`png`, `jpg/jpeg`, `webp`, `heic/heif`). MIME type
is inferred from the upload's content type, falling back to the file extension.

### Response `200` — `DocumentAdjudicationResponse`

```json
{
  "extractions": {
    "prescription": { "...": "ExtractedPrescription" },
    "medical_bill": { "...": "ExtractedMedicalBill" },
    "diagnostic_report": { "...": "ExtractedDiagnosticReport" },
    "pharmacy_bill": { "...": "ExtractedPharmacyBill" }
  },
  "decision": {
    "claim_id": "CLM_04217",
    "decision": "PARTIAL",
    "approved_amount": 8000.0,
    "rejection_reasons": [],
    "confidence_score": 0.92,
    "notes": "Root canal covered; teeth whitening excluded as cosmetic.",
    "next_steps": "Approved portion will be reimbursed; whitening is not covered."
  },
  "policy_context": { "limits": {}, "coverage": {}, "exclusions": [] },
  "agent_reports": {
    "coverage": { "findings": [], "excluded_amount": 4000.0, "summary": "..." },
    "necessity": { "findings": [], "summary": "..." },
    "validity": { "documents_consistent": true, "findings": [], "summary": "..." },
    "fraud": { "suspicion_level": "none", "findings": [], "summary": "..." }
  }
}
```

#### `decision` object (`AdjudicationDecision`)

| Field | Type | Notes |
|---|---|---|
| `claim_id` | string | Generated per request (`CLM_xxxxx`) |
| `decision` | enum | `APPROVED` · `REJECTED` · `PARTIAL` · `MANUAL_REVIEW` |
| `approved_amount` | number | INR; computed deterministically, capped at the billed amount |
| `rejection_reasons` | string[] | Codes; non-empty only when `decision = REJECTED` |
| `confidence_score` | number | 0.0–1.0 |
| `notes` | string | Key observations |
| `next_steps` | string | Guidance for the claimant |

- `extractions` mirrors the four `Extracted*` models (see `frontend/lib/types.ts` /
  `backend/models.py`). Documents that were not uploaded are omitted.
- `policy_context` is the per-claim policy slice retrieved from the graph (limits, relevant
  coverage categories, exclusions, applicable waiting periods, network hospitals).
- `agent_reports` contains each specialist's structured findings.

### Errors

| Status | When |
|---|---|
| `400` | Neither prescription nor medical bill uploaded |
| `500` | Adjudication graph failure (the message carries the cause) |

### Example

```bash
curl -X POST http://localhost:8000/adjudicate-documents \
  -F "member_id=EMP002" \
  -F "member_join_date=2024-01-15" \
  -F "claimed_amount=12000" \
  -F "prescription=@./prescription.jpg" \
  -F "medical_bill=@./bill.pdf"
```

---

## `GET /policy`

Returns the **active policy** as JSON. The policy is read from Neo4j (the source of truth),
falling back to the in-memory copy. The shape mirrors `policy_terms.json`.

**Response `200`** (abridged)
```json
{
  "policy_id": "PLUM_OPD_2024",
  "policy_name": "Plum OPD Insurance 2024",
  "effective_date": "2024-01-01",
  "coverage_details": {
    "per_claim_limit": 5000,
    "annual_limit": 50000,
    "family_floater_limit": 200000,
    "consultation_fees": { "covered": true, "sub_limit": 2000, "copay_percentage": 10, "network_discount": 20 },
    "diagnostic_tests": { "sub_limit": 10000 },
    "pharmacy": { "sub_limit": 15000 }
  },
  "claim_requirements": { "submission_timeline_days": 30, "minimum_claim_amount": 500 },
  "waiting_periods": { "initial_waiting": 30, "pre_existing_diseases": 365, "maternity": 365, "specific_ailments": {} },
  "exclusions": [],
  "network_hospitals": []
}
```

---

## `PUT /policy`

Replaces the active policy. The request body is the **full policy JSON** (same shape as
`GET /policy`). On success the backend, in one atomic step:

1. **validates** the structure,
2. **persists** the JSON to Neo4j and **rebuilds** the policy graph + cache, and
3. **refreshes** the rule engine's in-memory policy.

Changes apply immediately — no restart needed.

**Request body** (`application/json`) — the complete policy object.

**Constraints**

- `policy_id` is **immutable** and must remain `PLUM_OPD_2024` (it is the graph node key).
- Required keys (validated): `policy_name`, `effective_date`, `coverage_details`
  (`per_claim_limit`, `annual_limit`, `family_floater_limit`, `consultation_fees` with
  `sub_limit`/`copay_percentage`/`network_discount`, `diagnostic_tests.sub_limit`,
  `pharmacy.sub_limit`, plus `dental`/`vision`/`alternative_medicine`),
  `claim_requirements` (`submission_timeline_days`, `minimum_claim_amount`),
  `waiting_periods` (`initial_waiting`, `pre_existing_diseases`, `maternity`,
  `specific_ailments`), `exclusions` (list), `network_hospitals` (list).

**Response `200`** — the saved policy (same shape as `GET /policy`).

**Errors**

| Status | When |
|---|---|
| `422` | Validation failed (missing/invalid key, or `policy_id` changed); message names the problem |
| `500` | Failed to apply the policy (e.g. graph rebuild error) |

**Example**
```bash
curl -X PUT http://localhost:8000/policy \
  -H "Content-Type: application/json" \
  --data-binary @policy_terms.json
```

---

## Rejection codes

Codes that can appear in `rejection_reasons` (defined in `adjudication_rules.json`). Codes marked
**deterministic** are produced by the rule engine; **judgment** codes are added by the synthesis agent.

| Category | Code | Meaning | Source |
|---|---|---|---|
| Eligibility | `MEMBER_NOT_COVERED` | Claimant not found / inactive | deterministic |
| Eligibility | `WAITING_PERIOD` | Treatment during a waiting period | deterministic |
| Eligibility | `POLICY_INACTIVE` | Policy not active on treatment date | deterministic |
| Documentation | `MISSING_DOCUMENTS` | Required documents not submitted | deterministic |
| Documentation | `ILLEGIBLE_DOCUMENTS` | Document unreadable | deterministic |
| Documentation | `DOCTOR_REG_INVALID` | Registration number missing/wrong format | deterministic |
| Documentation | `DATE_MISMATCH` | Document dates don't match | judgment |
| Documentation | `PATIENT_MISMATCH` | Patient details don't match | judgment |
| Coverage | `SERVICE_NOT_COVERED` | Treatment excluded by policy | judgment |
| Coverage | `EXCLUDED_CONDITION` | Condition is in the exclusions list | judgment |
| Coverage | `PRE_AUTH_MISSING` | MRI/CT without pre-authorization | judgment |
| Limits | `PER_CLAIM_EXCEEDED` | Single-claim limit exceeded | deterministic |
| Limits | `ANNUAL_LIMIT_EXCEEDED` | Annual limit exhausted | deterministic |
| Limits | `SUB_LIMIT_EXCEEDED` | Category sub-limit exceeded | deterministic |
| Medical | `NOT_MEDICALLY_NECESSARY` | Treatment not justified by diagnosis | judgment |
| Medical | `COSMETIC_PROCEDURE` | Cosmetic / aesthetic procedure | judgment |
| Medical | `EXPERIMENTAL_TREATMENT` | Experimental / unproven treatment | judgment |
| Process | `LATE_SUBMISSION` | Submitted after the 30-day deadline | deterministic |
| Process | `DUPLICATE_CLAIM` | Same treatment already claimed | deterministic |
| Process | `BELOW_MIN_AMOUNT` | Claim below ₹500 minimum | deterministic |
