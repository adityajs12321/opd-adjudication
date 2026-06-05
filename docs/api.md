# API Documentation

Base URL (local): `http://localhost:8000`

All responses are JSON. CORS allowed origins are controlled by the `FRONTEND_URLS` env var
(comma-separated; defaults to `http://localhost:3000`). Allowed methods: `GET`, `POST`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness check |
| `POST` | `/members` | Create / upsert a member |
| `GET`  | `/members/{member_id}` | Fetch a member |
| `POST` | `/adjudicate-documents` | Adjudicate uploaded claim documents |

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
