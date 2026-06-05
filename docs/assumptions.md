# Assumptions

## Eligibility & membership

- **A claim must belong to a known member.** The member is created via `POST /members` first;
  an unknown or inactive member is a hard rejection (`MEMBER_NOT_COVERED`).
- **Join date drives waiting periods.** The member's stored `join_date` is preferred; the
  `member_join_date` form field is only a fallback when the stored date is absent.
- **Family floater** limit exists in the policy but is **not enforced** per-family in this build
  (only per-member annual and per-claim limits are applied).

## Documents

- **A prescription is mandatory** for every claim (it carries the doctor's registration and the
  diagnosis). A claim without one is `MISSING_DOCUMENTS`, even if a bill is present.
- **At least a prescription or a medical bill must be uploaded** for the endpoint to proceed.
- **Illegible vs incomplete are different.** A document that extracts to *nothing* is
  `ILLEGIBLE_DOCUMENTS`; a readable document merely missing one field is
  `INCOMPLETE_DOCUMENTATION` (a warning that does **not** block approval).
- **Doctor registration is validated by format only** — `[StateCode]/[Number]/[Year]`
  (regex `^[A-Z]{2,3}/\d+/\d{4}$`). There is no registry/database lookup of real doctors.
- **Patient-name and date consistency** across documents is left to the LLM validity agent
  (judgment), not the deterministic engine.

## Amounts

- **Approved amount never exceeds what was actually billed**, regardless of how line-item
  components were extracted (guards against the same amount landing in multiple fields).
- **The LLM never sets the rupee figure.** It decides the verdict and (via the coverage agent)
  estimates `excluded_amount`; the final number is computed deterministically from
  `max_approvable` and that excluded amount.
- **Copay applies to the consultation fee only** (10%), per the consultation sub-limit. The
  network discount is recorded in the analysis but **not currently subtracted** from the amount.
- **For partial claims, the excluded value is an LLM estimate** read from the bill's line items.
  If per-item costs are not itemized, the estimate is approximate — but the result can only go
  *down* from `max_approvable`, never above it.

## Coverage interpretation

- **Exclusions override everything.** If a base treatment is excluded, its consultation, tests,
  and medicines are excluded with it (a consultation is not independently approvable).
- **General OPD care is covered by default** — consultations, common tests, prescribed medicines,
  standard procedures — without requiring an itemized cost breakdown (lenient-by-default coverage).
- **Category mapping is keyword/LLM-driven**: dental (cosmetic excluded), vision (LASIK excluded),
  alternative medicine (Ayurveda/Homeopathy/Unani covered, incl. Panchakarma; Naturopathy/Siddha
  excluded). The rule engine does **not** enforce per-category sub-limits beyond consultation,
  pharmacy, and diagnostics; finer category coverage is the coverage agent's judgment.

## Dates & timing

- **Submission deadline (30 days)** is measured from the bill date to *today*.
- **Initial waiting period (30 days)** is measured from join date to the treatment date — distinct
  from the submission deadline, even though both are 30 days.
- **Condition-specific waiting periods** rely on `canonical_conditions` extracted by the LLM
  (e.g. "Type 2 DM" → `diabetes`) rather than fragile substring matching on free-text diagnosis.

## Pre-authorization

- **MRI and CT scans require pre-authorization.** Detected deterministically by keyword; since the
  system has no record of whether pre-auth was actually obtained, it **assumes pre-auth was not
  obtained** and rejects with `PRE_AUTH_MISSING`.

## Fraud

- The fraud agent only sees the current claim's documents and amounts. Cross-claim signals that
  require external context — e.g. **"multiple claims same day"** — are **not detected**, because
  that count is not captured or passed into the pipeline. Same-bill/same-date duplicates *are*
  caught deterministically via the Postgres duplicate check.

## LLM / infrastructure

- **Model:** `gemini-2.5-flash` with `temperature=0` for repeatability. Output is parsed by
  `model_validate_json` (no `response_schema`, which Gemini rejects for these models due to
  `additionalProperties`).
- **Gemini calls retry** transient failures (429 / 5xx) with exponential backoff + jitter; a
  rate-limited extraction is retried rather than being mistaken for an illegible document.
- **The policy graph is built once at startup** and cached in memory; adjudication does no live
  Neo4j queries. The cache is not invalidated until the next restart, so policy edits require a
  backend restart.
- **Postgres and Neo4j are both required** at startup (`init_db`, `init_graph`); there is no
  in-memory fallback if either is unavailable.

## Known test-data caveats

- **TC005** (waiting period) is internally inconsistent: its own note says eligibility begins
  2024-11-30, yet the treatment date is in 2026, so the waiting period is actually satisfied. The
  system correctly does **not** reject it; the fixture's expected `REJECTED` is wrong.
