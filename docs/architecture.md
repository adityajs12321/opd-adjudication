# Architecture

The system is a Next.js frontend talking to a FastAPI backend. The backend combines a
deterministic **rule engine** with an LLM-based **multi-agent adjudicator** (LangGraph + Gemini),
backed by **PostgreSQL** (claim/member state) and **Neo4j** (the policy stored as a graph).

## High-level component diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (Next.js)                              │
│   / welcome + register   /adjudicate upload + results   /policy editor        │
│   app/components/CreateMemberModal.tsx        lib/types.ts — TS models        │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │ HTTPS (multipart / JSON)
                                    ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                              Backend (FastAPI · main.py)                          │
│                                                                                   │
│   POST /adjudicate-documents   POST /members   GET /members/{id}   GET /health    │
│   GET/PUT /policy                                                                 │
│                                                                                   │
│   ┌────────────┐   ┌────────────────┐   ┌─────────────────┐   ┌────────────────┐  │
│   │ Extraction │──▶│ Rule engine    │──▶│ Policy retrieval│──▶│ Adjudication   │  │
│   │ (Gemini)   │   │ (deterministic)│   │ (Neo4j cache)   │   │ (LangGraph)    │  │
│   └─────┬──────┘   └──────┬─────────┘   └───────┬─────────┘   └───────┬────────┘  │
│         │                 │                     │                     │           │
└─────────┼─────────────────┼─────────────────────┼─────────────────────┼───────────┘
          │                 │                     │                     │
          ▼                 ▼                     ▼                     ▼
    ┌──────────┐      ┌──────────┐          ┌──────────┐          ┌──────────┐
    │  Gemini  │      │ Postgres │          │  Neo4j   │          │  Gemini  │
    │   API    │      │ (claims, │          │ (policy  │          │   API    │
    │          │      │ members) │          │  graph)  │          │ (agents) │
    └──────────┘      └──────────┘          └──────────┘          └──────────┘
```

## End-to-end flowchart

```
                         ┌──────────────────────┐
                         │  Claim documents in  │
                         └───────────┬──────────┘
                                     ▼
                         ┌──────────────────────┐
                         │   Rule engine runs   │
                         └───────────┬──────────┘
                                     ▼
                    ┌────────────────────────────────┐
                    │      Any hard rejection?       │
                    └───────┬───────────────┬────────┘
                       yes  │               │ no
                            ▼               ▼
                    ┌──────────────┐  ┌──────────────────────────┐
                    │  REJECTED    │  │  Run 4 specialist agents │
                    │  amount = 0  │  │  (coverage/necessity/    │
                    │  + codes     │  │   validity/fraud)        │
                    └──────────────┘  └─────────────┬────────────┘
                                                    ▼
                                      ┌──────────────────────────┐
                                      │    Synthesis verdict     │
                                      └──┬────────┬────────┬─────┘
                            all covered  │  mixed │  all   │ high fraud/
                                         ▼        ▼ excl.  ▼ ambiguous
                                  ┌──────────┐ ┌────────┐ ┌──────────┐ ┌──────────────┐
                                  │ APPROVED │ │PARTIAL │ │ REJECTED │ │ MANUAL_REVIEW│
                                  │ = max    │ │= max − │ │   = 0    │ │     = 0      │
                                  │  apprv.  │ │ excl.  │ │          │ │              │
                                  └──────────┘ └───┬────┘ └──────────┘ └──────────────┘
                                                   │ nets to 0?
                                                   └────────────▶ REJECTED
```

## Multi-agent adjudication graph (`adjudication_graph.py`)

Four specialist agents run **in parallel** (fan-out from `START`), each receiving only the
inputs it needs. Their structured reports converge on a single **Synthesis** node that merges
them with the deterministic rule-engine findings and emits the final decision.

```
                         ┌───────────────────────┐
                  ┌─────▶│ Coverage              │──────┐
                  │      │ covered / excluded +  │      │
                  │      │ excluded_amount       │      │
                  │      └───────────────────────┘      │
                  │      ┌───────────────────────┐      │
                  │ ┌───▶│ Medical Necessity     │────┐ │
   START ─────────┼─┤    └───────────────────────┘    │ │
   (claim_id,     │ │    ┌───────────────────────┐    │ ▼
    docs,         │ ├───▶│ Document Validity     │──▶ Synthesis ──▶ END
    policy slice, │ │    └───────────────────────┘    ▲ (merge + deterministic
    rule findings)│ │    ┌───────────────────────┐    │  amount + guardrails)
                  │ └───▶│ Fraud                 │────┘ │
                  │      └───────────────────────┘      │
                  └─────────────────────────────────────┘
```

- **Coverage** — is each treatment covered? Applies category cues and the exclusion list;
  exclusions cascade to the consultation/tests/medicines that ride on an excluded treatment.
  Also estimates `excluded_amount` (rupee value of excluded items) for partial deductions.
- **Medical Necessity** — is the treatment reasonable for the diagnosis?
- **Document Validity** — registration format, name/date consistency, tampering signs.
- **Fraud** — matches known fraud indicators against the documents and amounts.
- **Synthesis** — picks the verdict (`APPROVED / REJECTED / PARTIAL / MANUAL_REVIEW`).
  Hard rejections from the rule engine override a softer LLM verdict. The **rupee amount is
  computed deterministically here** (see `decision-logic.md`), not taken from the LLM.

### Why the split (deterministic vs LLM)

| Concern | Owner | Why |
|---|---|---|
| Limits, copay, dates, waiting periods, doc presence | Rule engine | Must be exact & reproducible |
| Coverage, necessity, validity, fraud (judgment) | LLM agents | Needs natural-language understanding |

## Reliability mechanisms

- **Retries with exponential backoff + jitter** on every Gemini call (extraction and agents)
  for rate limits (429) and transient 5xx errors.
- **`temperature=0`** on extraction and adjudication calls for repeatable output.
- **Neo4j cached in memory** — the policy graph is read into an in-memory cache on startup and
  per-claim retrieval filters that cache, so adjudication does no live graph round-trips. A policy
  edit (`PUT /policy`) rebuilds the graph and refreshes the cache, so no restart is needed.
- **Deterministic guardrails** in synthesis: amount capped at `max_approvable`; hard rejections
  force `REJECTED`; a partial that nets to ₹0 collapses to `REJECTED`.

## Data stores

| Store | Holds | Notes |
|---|---|---|
| **Postgres** | `members`, `claims`, `claim_documents` | Annual spend, duplicate detection, audit of extracted data |
| **Neo4j** | Policy graph (`PLUM_OPD_2024`) — **source of truth** | Limits, coverage categories, exclusions, waiting periods, network hospitals; full source JSON kept on the root node's `raw_json` for lossless read-back |

The policy graph is seeded from `policy_terms.json` only when Neo4j is empty; afterwards edits via
`PUT /policy` persist in Neo4j and survive restarts. See `database.py` for the SQL schema and
`graph_store.py` for the graph model.

## Deployment topology

Automated deployment to Vercel and Render native Git integration.

| Component | Host |
|---|---|
| Frontend | Vercel (root dir `frontend`) |
| Backend | Render (`render.yaml`, root dir `backend`) |
| Postgres | Supabase |
| Neo4j | Neo4j AuraDB |
