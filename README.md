# OPD Claim Adjudication Tool

AI-powered OPD (outpatient) insurance claim adjudication against policy **PLUM_OPD_2024**.
A claimant uploads their claim documents (prescription, medical bill, diagnostic report,
pharmacy bill); the system extracts the data, runs deterministic policy checks, and produces
a structured decision — `APPROVED`, `REJECTED`, `PARTIAL`, or `MANUAL_REVIEW` — with the
approved amount, rejection codes, confidence score, and step-by-step reasoning.

Documentation is in the [Docs](https://github.com/adityajs12321/opd-adjudication/tree/main/docs) folder

Backend is hosted on Render, so it will take a few seconds to wake up if not accessed recently.

## Features

**Adjudication**
- **Multi-document claim intake** — upload a prescription, medical bill, diagnostic report, and
  pharmacy bill (images or PDF); a prescription or medical bill is mandatory.
- **AI document extraction** — each document is parsed by Gemini into a structured model
  (doctor, registration, diagnosis, line items, amounts, medicines, tests, etc.), with
  retry-with-backoff so a rate-limited extraction is retried rather than mistaken for an
  illegible document.
- **Hybrid decision engine** — a deterministic rule engine handles everything numeric/date-based;
  four LLM specialist agents (Coverage, Medical Necessity, Document Validity, Fraud) run in
  parallel and a Synthesis node merges their findings with the rule-engine output.
- **Deterministic amounts** — the LLM decides the verdict; the approved rupee figure is computed
  in code and can never exceed `max_approvable` or the actual billed total.
- **Policy-aware retrieval** — the policy lives in a Neo4j graph (the source of truth); only the
  relevant slice is retrieved per claim and shown in the UI.
- **Structured decisions** — every claim returns `APPROVED | REJECTED | PARTIAL | MANUAL_REVIEW`
  with approved amount, rejection codes, confidence score, notes, and next steps.

**Policy enforcement**
- Per-claim, annual, and category sub-limits; consultation copay; minimum-claim amount.
- Initial and condition-specific waiting periods; 30-day submission deadline.
- Pre-authorization checks (MRI / CT) and duplicate-claim detection.
- Exclusion cascade — if a base treatment is excluded, its consultation, tests, and medicines
  are excluded with it.

**Members & data**
- **Create members from the UI** — a "Register New Member" modal posts to `POST /members`
  (member ID, name, join date, relationship) and pre-fills the claim form on success.
- Member eligibility and join-date driven waiting periods; claims and documents persisted in
  PostgreSQL.

**Policy management**
- **View & edit the policy from the UI** — a dedicated policy editor page (`/policy`) loads the
  active policy via `GET /policy` and saves edits via `PUT /policy`.
- **Neo4j is the source of truth** — the policy is seeded from `policy_terms.json` only when the
  graph is empty; thereafter edits are persisted in Neo4j and survive restarts/redeploys.
- **Edits apply live, no restart** — saving validates the policy, rebuilds the Neo4j graph, and
  refreshes the rule engine's in-memory copy in one atomic step. `policy_id` is immutable.

**Frontend UX**
- **Welcome page** (`/`) with a member registration window; the claim tool lives at `/adjudicate`
  and the policy editor at `/policy`.
- Drag-to-click upload boxes with per-document status, collapsible extracted-data cards, a
  retrieved-policy-terms panel, and a decision banner with confidence bar and computed copay.

## How it works

The adjudication pipeline is a hybrid of deterministic rules and LLM judgment:

```
documents ─▶ extraction ─▶ rule engine ─▶ policy retrieval ─▶ multi-agent adjudication ─▶ decision
            (Gemini)       (numeric /      (Neo4j graph)       (LangGraph: 4 specialists
                            date checks)                        + synthesis)
```

1. **Extraction** — each uploaded document is sent to Gemini in parallel and parsed into a
   structured Pydantic model.
2. **Rule engine** (`rule_engine.py`) — deterministic, no LLM. Handles everything numeric or
   date-based: per-claim / annual / sub-limits, copay, waiting periods, submission deadline,
   missing/illegible documents, duplicate claims, member eligibility, doctor-registration
   format, pre-auth flags. Produces a `max_approvable` ceiling and a suggested decision.
3. **Policy retrieval** (`graph_store.py`) — the policy is stored in Neo4j as a graph (seeded from `policy_terms.json` on first run and editable via `/policy`); per claim,
   only the relevant policy nodes are retrieved and passed to the agents.
4. **Multi-agent adjudication** (`adjudication_graph.py`) — a LangGraph workflow runs four
   specialist agents in parallel — **Coverage**, **Medical Necessity**, **Document Validity**,
   **Fraud** — then a **Synthesis** node merges their findings with the rule-engine output.
   The final approved amount is computed deterministically (it can never exceed `max_approvable`
   or the actual billed amount), so the LLM decides the verdict but not the rupee figure.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Backend | FastAPI |
| LLM | Google Gemini |
| Orchestration | LangGraph (multi-agent) |
| Database | PostgreSQL (members, claims, claim documents) |
| Policy graph | Neo4j |

## Project structure

```
backend/
  main.py               # FastAPI app — endpoints + pipeline orchestration
  rule_engine.py        # Deterministic pre-processing (limits, dates, docs)
  document_extractor.py # Per-document Gemini extraction
  adjudication_graph.py # LangGraph multi-agent adjudication + synthesis
  graph_store.py        # Neo4j policy graph build + per-claim retrieval
  database.py           # Postgres access (members, claims, documents)
  models.py             # Pydantic models
  requirements.txt
frontend/
  app/
    page.tsx                     # Welcome page + member registration window
    adjudicate/page.tsx          # Claim upload form + results
    policy/page.tsx              # Policy viewer / editor
    components/CreateMemberModal.tsx  # Shared member-registration modal
    layout.tsx, globals.css
  lib/types.ts          # TypeScript mirrors of the Pydantic models
  package.json
document_generator/     # Mock document generator (PNG/PDF + ground-truth JSON)
  generator.py          # PNG generators + batch/claim/test-case helpers
  pdf_generator.py      # Text-based PDF generators (reportlab)
  data.py               # Sample pools, ClaimContext, bill-layout templates
  README.md             # Full generator docs
policy_terms.json       # Coverage limits, sub-limits, exclusions, network hospitals (seeds Neo4j)
adjudication_rules.json # Adjudication logic + rejection codes (read by backend)
test_cases.json         # 10 test scenarios
render.yaml             # Render Blueprint for backend deploy
```

## Prerequisites

- **Python 3.12+** and **Node.js 18+**
- A **Google Gemini API key** — https://aistudio.google.com/apikey
- A running **PostgreSQL** instance
- A running **Neo4j** instance (local Neo4j Desktop, or Neo4j AuraDB)

## Setup

### 0. Neo4j (via Docker)

If you don't already have Neo4j running, the quickest way is Docker. This starts a local instance
with the credentials the backend expects:

```bash
docker run -d \
  --name plum-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_neo4j_password \
  neo4j:5
```

- `7687` is the Bolt port the backend connects to (`NEO4J_URI=bolt://localhost:7687`).
- `7474` is the Neo4j Browser UI — open http://localhost:7474 to inspect the policy graph.
- Set `NEO4J_AUTH=neo4j/<password>` to whatever you put in `backend/.env` as `NEO4J_PASSWORD`
  (the username must be `neo4j`).

Manage the container with `docker stop plum-neo4j` / `docker start plum-neo4j`. To wipe it and
start fresh, `docker rm -f plum-neo4j` and re-run the command above. The policy graph is
(re)built automatically by the backend on startup.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env                                 # then edit .env with your values
```

Edit `backend/.env`:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_URL=postgresql://postgres:password@localhost:5432/opd
NEO4J_URI=bolt://localhost:7687          # neo4j+s://... for AuraDB
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
FRONTEND_URLS=http://localhost:3000      # comma-separated for multiple origins
```

Run the dev server (tables and the policy graph are initialized automatically on startup):

```bash
uvicorn main:app --reload   # http://localhost:8000
```

### 2. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```ini
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Run the dev server:

```bash
npm run dev   # http://localhost:3000
```

## Usage

1. Open http://localhost:3000 — the welcome page.
2. **Register a member** in the registration window (a claim must belong to a known member). This
   posts to `POST /members`; on success you can jump straight to a claim.
3. On the **claim page** (`/adjudicate`), enter the member ID, upload the claim documents, and
   submit. The result panel shows the decision, approved amount, rejection codes, confidence, and
   the specialist agents' reasoning.
4. (Optional) Open the **policy editor** (`/policy`) to view or edit the active policy. Saving
   rebuilds the Neo4j graph and rule engine live — no restart needed.

## Decision schema

Every adjudication returns:

- `decision` — `APPROVED | REJECTED | PARTIAL | MANUAL_REVIEW`
- `approved_amount` — INR approved (computed deterministically, capped at the billed amount)
- `rejection_reasons` — error codes (e.g. `PER_CLAIM_EXCEEDED`, `WAITING_PERIOD`,
  `SERVICE_NOT_COVERED`, `PRE_AUTH_MISSING`)
- `confidence_score` — 0.0–1.0
- `notes`, `next_steps`

## Testing

`test_cases.json` contains 10 canonical scenarios (approvals, partial approvals, limit/waiting-period
rejections, excluded treatments, pre-auth, fraud review) used to verify adjudication behavior.

## Document generator

`document_generator/` is a standalone package that produces realistic mock claim documents
to test the extraction + adjudication pipeline end-to-end without hand-collecting real paperwork.
See [`document_generator/README.md`](document_generator/README.md) for full details.

**Features**
- **Four document types** — prescription, medical bill/invoice, diagnostic report, pharmacy bill.
- **PNG and PDF output** — raster PNGs with visual OCR stressors, or real selectable-text PDFs
  (reportlab); `--format both` emits both with identical data so they share one ground-truth JSON.
- **Ground-truth sidecars** — every document gets a `*.json` mirroring `backend/models.py`, so you
  can diff Gemini's extraction against exactly what was printed.
- **Three generation modes** — randomized standalone documents (`batch`), a coherent 4-document
  claim set with shared patient/doctor/diagnosis (`claim`), or a prescription + bill for each
  scenario in `test_cases.json` so the documents match the expected decision (`testcases`).
- **Realism variations** — handwritten / multilingual headers, fading, blur, skew, noise, JPEG
  artifacts, stamps, signatures, pen corrections, truncation; bills also show cancelled items and
  part payments (total-preserving) plus multiple-patient and refund edge cases.
- **Per-hospital bill layouts** — each medical bill renders in one of three structurally distinct
  templates (`classic` / `compact` / `itemised`), chosen deterministically from the hospital name,
  to exercise extraction against varied invoice formats.

**Usage**

```bash
pip install -r document_generator/requirements.txt

python -m document_generator batch --count 25 --format both          # 25 random documents
python -m document_generator claim --format pdf                      # one coherent claim set
python -m document_generator testcases --format both                 # docs for every test case
python -m document_generator testcases --cases TC002 TC005           # only specific cases
python -m document_generator single --type prescription \
    --variations handwritten stamp signature                         # one document, chosen variations
```

## Deployment

The app is designed to deploy as: frontend on **Vercel** (root directory `frontend`), backend on
**Render** (see `render.yaml`, root directory `backend`), Postgres on **Supabase**, and the policy
graph on **Neo4j AuraDB**.

## LICENCE

MIT