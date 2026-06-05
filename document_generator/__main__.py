from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .generator import (
    ALL_VARIATIONS, _GENERATORS, _get_pdf_generators, _save,
    generate_batch, generate_claim_set, generate_test_cases,
)

_FORMAT_CHOICES = ["png", "pdf", "both"]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="document_generator", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("batch", help="generate N randomized standalone documents")
    b.add_argument("--count", type=int, default=25)
    b.add_argument("--out", default="generated_documents")
    b.add_argument("--seed", type=int, default=None)
    b.add_argument("--types", nargs="*", choices=list(_GENERATORS), default=None)
    b.add_argument("--format", choices=_FORMAT_CHOICES, default="png",
                   help="output format: png (default), pdf, or both")

    cl = sub.add_parser("claim", help="generate one coherent 4-document claim set")
    cl.add_argument("--out", default="generated_documents/claim")
    cl.add_argument("--seed", type=int, default=None)
    cl.add_argument("--format", choices=_FORMAT_CHOICES, default="png",
                    help="output format: png (default), pdf, or both")

    s = sub.add_parser("single", help="generate a single document")
    s.add_argument("--type", required=True, choices=list(_GENERATORS))
    s.add_argument("--out", default="generated_documents")
    s.add_argument("--variations", nargs="*", choices=ALL_VARIATIONS, default=None,
                   help=f"any of: {', '.join(ALL_VARIATIONS)}")
    s.add_argument("--seed", type=int, default=None)
    s.add_argument("--format", choices=_FORMAT_CHOICES, default="png",
                   help="output format: png (default), pdf, or both")

    tc = sub.add_parser("testcases",
                        help="generate prescription + bill for each test_cases.json entry")
    tc.add_argument("--out", default="generated_documents/test_cases")
    tc.add_argument("--seed", type=int, default=42,
                    help="base seed (each case gets base_seed + case_index)")
    tc.add_argument("--format", choices=_FORMAT_CHOICES, default="png",
                    help="output format: png (default), pdf, or both")
    tc.add_argument("--cases", nargs="*", default=None,
                    help="specific case ids to generate, e.g. TC002 TC005 (default: all)")

    args = p.parse_args(argv)

    if args.cmd == "batch":
        m = generate_batch(args.count, args.out, args.seed, args.types, fmt=args.format)
        _report_batch(m, args.out)

    elif args.cmd == "claim":
        m = generate_claim_set(args.out, args.seed, fmt=args.format)
        ctx = m["claim_context"]
        print(f"Wrote {args.format.upper()} claim for {ctx['patient_name']} "
              f"({ctx['diagnosis']}) to {args.out}/")

    elif args.cmd == "testcases":
        m = generate_test_cases(args.out, base_seed=args.seed, fmt=args.format,
                                case_ids=args.cases)
        n = len(m["test_cases"])
        docs_per_case = sum(len(tc["documents"]) for tc in m["test_cases"])
        print(f"Wrote {docs_per_case} documents for {n} test cases to {args.out}/ (+ manifest.json)")
        for tc in m["test_cases"]:
            doc_labels = ", ".join(tc["documents"].keys())
            print(f"  {tc['case_id']}: {tc['case_name']} [{tc['expected_decision']}] — {doc_labels}")

    elif args.cmd == "single":
        rng = random.Random(args.seed)
        doc_type = args.type
        fmt = args.format
        variations = args.variations   # None = pick randomly

        img = pdf_bytes = gt = None

        if fmt in ("png", "both"):
            pre_state = rng.getstate()
            img, gt = _GENERATORS[doc_type](rng=rng, variations=variations)

        if fmt in ("pdf", "both"):
            if fmt == "both":
                rng.setstate(pre_state)   # same rng state → identical document data
            pdf_bytes, gt_pdf = _get_pdf_generators()[doc_type](rng=rng, variations=variations)
            if fmt == "pdf":
                gt = gt_pdf

        out_dir = Path(args.out)
        rec = _save(img, pdf_bytes, gt, out_dir, doc_type)
        for key in ("image", "pdf"):
            if key in rec:
                print(f"Wrote {rec[key]}")
        print(json.dumps(gt["ground_truth"], indent=2, ensure_ascii=False))


def _report_batch(m: dict, out: str) -> None:
    n = len(m["documents"])
    fmt = m.get("format", "png")
    exts = {"png": ".png", "pdf": ".pdf", "both": ".png + .pdf"}[fmt]
    print(f"Wrote {n} documents ({exts}) to {out}/ (+ manifest.json)")


if __name__ == "__main__":
    main()
