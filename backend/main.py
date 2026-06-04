import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

from models import AdjudicationDecision, ClaimRequest

load_dotenv()

app = FastAPI(title="Plum OPD Adjudication API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

# Load policy context once at startup
ROOT = Path(__file__).parent.parent
_policy = (ROOT / "policy_terms.json").read_text()
_rules = (ROOT / "adjudication_rules.md").read_text()

SYSTEM_PROMPT = f"""You are an expert OPD insurance claim adjudicator for Plum Insurance. \
Evaluate claims strictly and accurately against the provided policy terms and adjudication rules.

## POLICY TERMS
```json
{_policy}
```

## ADJUDICATION RULES
{_rules}

Follow the 5-step adjudication flow: eligibility → document validation → coverage verification \
→ limit validation → medical necessity. Apply all copay percentages, network discounts, and \
sub-limits correctly. When in doubt, flag for manual review.

You MUST return a JSON object with ALL of these fields:
- claim_id (string)
- decision: one of "APPROVED", "REJECTED", "PARTIAL", "MANUAL_REVIEW"
- approved_amount (number, 0 for full rejections)
- rejection_reasons (array of code strings, empty array if approved)
- confidence_score (number 0.0–1.0)
- notes (string, brief observation)
- next_steps (string, what the claimant should do)
- reasoning (string, detailed step-by-step explanation of your decision)
- deductions (object like {{"copay": 150}}, omit if none)
- network_discount (number, omit if not applicable)
- cashless_approved (boolean, only for cashless requests)
- rejected_items (array of strings like "Teeth whitening - cosmetic procedure", omit if none)
- flags (array of strings for fraud/review flags, omit if none)"""

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/adjudicate", response_model=AdjudicationDecision)
def adjudicate(claim: ClaimRequest):
    claim_id = f"CLM_{int(time.time() * 1000) % 100000:05d}"

    user_message = (
        f'Adjudicate this OPD insurance claim. Use claim_id "{claim_id}".\n\n'
        f"```json\n{claim.model_dump_json(indent=2, exclude_none=True)}\n```"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
            ),
        )
        return AdjudicationDecision.model_validate_json(response.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
