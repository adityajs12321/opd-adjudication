import os

from neo4j import GraphDatabase

from models import ExtractionResults

POLICY_ID = "PLUM_OPD_2024"

_driver = None
_cache: dict = {}   # full graph loaded into memory once after init


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
        )
    return _driver


# ── Graph initialisation ──────────────────────────────────────────────────────

def init_graph(policy_data: dict):
    """Clear and rebuild the policy graph, then warm the in-memory cache."""
    global _cache
    with _get_driver().session() as session:
        session.execute_write(_build_graph, policy_data)
    _cache = _load_cache()


def _build_graph(tx, policy: dict):
    pid = policy["policy_id"]
    cov = policy["coverage_details"]

    # Wipe previous graph (all nodes carry the PlumPolicyNode marker label)
    tx.run("MATCH (n:PlumPolicyNode) DETACH DELETE n")

    # ── Policy root ───────────────────────────────────────────────────────────
    tx.run(
        """
        CREATE (:Policy:PlumPolicyNode {id: $id, name: $name, effective_date: $eff})
        """,
        id=pid,
        name=policy["policy_name"],
        eff=policy["effective_date"],
    )

    # ── Global limits ─────────────────────────────────────────────────────────
    tx.run(
        """
        MATCH (p:Policy {id: $pid})
        CREATE (l:Limit:PlumPolicyNode {
            per_claim: $per_claim,
            annual: $annual,
            family_floater: $family_floater
        })
        CREATE (p)-[:HAS_LIMIT]->(l)
        """,
        pid=pid,
        per_claim=cov["per_claim_limit"],
        annual=cov["annual_limit"],
        family_floater=cov["family_floater_limit"],
    )

    # ── Claim requirements ────────────────────────────────────────────────────
    cr = policy["claim_requirements"]
    tx.run(
        """
        MATCH (p:Policy {id: $pid})
        CREATE (r:ClaimRequirement:PlumPolicyNode {
            submission_deadline_days: $deadline,
            minimum_claim_amount: $min_amount
        })
        CREATE (p)-[:HAS_CLAIM_REQUIREMENT]->(r)
        """,
        pid=pid,
        deadline=cr["submission_timeline_days"],
        min_amount=cr["minimum_claim_amount"],
    )

    # ── Coverage categories ───────────────────────────────────────────────────
    category_map = {
        "consultation_fees": cov["consultation_fees"],
        "diagnostic_tests": cov["diagnostic_tests"],
        "pharmacy": cov["pharmacy"],
        "dental": cov["dental"],
        "vision": cov["vision"],
        "alternative_medicine": cov["alternative_medicine"],
    }

    # Keys that become child nodes instead of flat properties
    _list_children = {
        "covered_tests": "CoveredTest",
        "procedures_covered": "CoveredProcedure",
        "covered_treatments": "CoveredTreatment",
    }

    for cat_name, cat_data in category_map.items():
        props = {k: v for k, v in cat_data.items() if k not in _list_children}
        props["name"] = cat_name

        tx.run(
            """
            MATCH (p:Policy {id: $pid})
            CREATE (c:CoverageCategory:PlumPolicyNode $props)
            CREATE (p)-[:HAS_COVERAGE]->(c)
            """,
            pid=pid,
            props=props,
        )

        for list_key, node_label in _list_children.items():
            for item in cat_data.get(list_key, []):
                tx.run(
                    f"""
                    MATCH (c:CoverageCategory {{name: $cat}})
                    CREATE (i:{node_label}:PlumPolicyNode {{name: $name}})
                    CREATE (c)-[:COVERS]->(i)
                    """,
                    cat=cat_name,
                    name=item,
                )

    # ── Waiting periods ───────────────────────────────────────────────────────
    wp = policy["waiting_periods"]
    for wp_type, days in [
        ("initial", wp["initial_waiting"]),
        ("pre_existing_diseases", wp["pre_existing_diseases"]),
        ("maternity", wp["maternity"]),
    ]:
        tx.run(
            """
            MATCH (p:Policy {id: $pid})
            CREATE (w:WaitingPeriod:PlumPolicyNode {type: $type, days: $days})
            CREATE (p)-[:HAS_WAITING_PERIOD]->(w)
            """,
            pid=pid,
            type=wp_type,
            days=days,
        )

    for condition, days in wp["specific_ailments"].items():
        tx.run(
            """
            MATCH (p:Policy {id: $pid})
            CREATE (w:WaitingPeriod:PlumPolicyNode {type: 'specific_ailment', days: $days})
            CREATE (cond:Condition:PlumPolicyNode {name: $condition})
            CREATE (p)-[:HAS_WAITING_PERIOD]->(w)
            CREATE (w)-[:APPLIES_TO]->(cond)
            """,
            pid=pid,
            days=days,
            condition=condition,
        )

    # ── Exclusions ────────────────────────────────────────────────────────────
    for excl in policy["exclusions"]:
        tx.run(
            """
            MATCH (p:Policy {id: $pid})
            CREATE (e:Exclusion:PlumPolicyNode {description: $desc})
            CREATE (p)-[:EXCLUDES]->(e)
            """,
            pid=pid,
            desc=excl,
        )

    # ── Network hospitals ─────────────────────────────────────────────────────
    for hospital in policy["network_hospitals"]:
        tx.run(
            """
            MATCH (p:Policy {id: $pid})
            CREATE (h:NetworkHospital:PlumPolicyNode {name: $name})
            CREATE (p)-[:NETWORK_HOSPITAL]->(h)
            """,
            pid=pid,
            name=hospital,
        )


# ── Startup cache load ────────────────────────────────────────────────────────

def _load_cache() -> dict:
    """Read the full policy graph from Neo4j into a plain Python dict once."""
    cache: dict = {}
    with _get_driver().session() as session:

        row = session.run(
            """
            MATCH (p:Policy {id: $pid})-[:HAS_LIMIT]->(l:Limit)
            MATCH (p)-[:HAS_CLAIM_REQUIREMENT]->(r:ClaimRequirement)
            RETURN l {.*} AS limits, r {.*} AS claim_requirements
            """,
            pid=POLICY_ID,
        ).single()
        if row:
            cache["limits"] = dict(row["limits"])
            cache["claim_requirements"] = dict(row["claim_requirements"])

        rows = session.run(
            """
            MATCH (p:Policy {id: $pid})-[:HAS_COVERAGE]->(c:CoverageCategory)
            OPTIONAL MATCH (c)-[:COVERS]->(item)
            RETURN c {.*} AS category, collect(item.name) AS covered_items
            """,
            pid=POLICY_ID,
        ).data()
        cache["coverage"] = {}
        for row in rows:
            cat = dict(row["category"])
            cat_name = cat.pop("name")
            items = [i for i in row["covered_items"] if i]
            if items:
                cat["covered_items"] = items
            cache["coverage"][cat_name] = cat

        excl_row = session.run(
            "MATCH (p:Policy {id: $pid})-[:EXCLUDES]->(e:Exclusion) RETURN collect(e.description) AS ex",
            pid=POLICY_ID,
        ).single()
        if excl_row:
            cache["exclusions"] = excl_row["ex"]

        wp_rows = session.run(
            """
            MATCH (p:Policy {id: $pid})-[:HAS_WAITING_PERIOD]->(w:WaitingPeriod)
            OPTIONAL MATCH (w)-[:APPLIES_TO]->(cond:Condition)
            RETURN w.type AS type, w.days AS days, cond.name AS condition
            """,
            pid=POLICY_ID,
        ).data()
        cache["waiting_periods"] = {"general": {}, "specific": {}}
        for row in wp_rows:
            if row["condition"]:
                cache["waiting_periods"]["specific"][row["condition"]] = row["days"]
            else:
                cache["waiting_periods"]["general"][row["type"]] = row["days"]

        h_row = session.run(
            "MATCH (p:Policy {id: $pid})-[:NETWORK_HOSPITAL]->(h:NetworkHospital) RETURN collect(h.name) AS hospitals",
            pid=POLICY_ID,
        ).single()
        if h_row:
            cache["network_hospitals"] = h_row["hospitals"]

    return cache


# ── Per-claim filtering (no Neo4j round-trip) ─────────────────────────────────

def query_relevant_policy(extractions: ExtractionResults) -> dict:
    """
    Traverse the policy graph and return only the nodes relevant to this claim.
    The result replaces the full policy JSON in the LLM system prompt.
    """
    bill = extractions.medical_bill
    rx = extractions.prescription
    pharmacy = extractions.pharmacy_bill
    diagnostic = extractions.diagnostic_report

    # ── Determine relevant coverage categories from extracted claim data ─────
    relevant_categories: set[str] = set()

    if bill:
        if bill.consultation_fee > 0:
            relevant_categories.add("consultation_fees")
        if bill.other_charges > 0:
            relevant_categories.add("diagnostic_tests")
    if pharmacy:
        relevant_categories.add("pharmacy")
    if diagnostic:
        relevant_categories.add("diagnostic_tests")
    if rx and rx.tests_advised:
        relevant_categories.add("diagnostic_tests")

    diagnosis = (rx.diagnosis if rx else "").lower()
    medicines_text = " ".join(rx.medicines_prescribed if rx else []).lower()
    procedures_text = " ".join(rx.procedures if rx else []).lower()
    doctor_name = (rx.doctor_name if rx else "").lower()
    doctor_reg = (rx.doctor_registration if rx else "").lower()
    context_text = f"{diagnosis} {medicines_text} {procedures_text} {doctor_name} {doctor_reg}"

    keyword_to_category = {
        "dental": ["dental", "tooth", "teeth", "gum", "oral", "cavity", "root canal"],
        "vision": ["eye", "vision", "optical", "glasses", "cataract", "myopia", "retina"],
        "alternative_medicine": [
            "ayurveda", "ayur", "homeopathy", "homeo", "unani", "siddha", "naturo",
            "panchakarma", "vaidya", "herbal", "alternative",
        ],
    }
    for category, keywords in keyword_to_category.items():
        if any(kw in context_text for kw in keywords):
            relevant_categories.add(category)

    # Use canonical_conditions (LLM-normalised) for reliable waiting period lookup
    canonical = {c.lower() for c in (rx.canonical_conditions if rx else [])}
    condition_keywords = ["diabetes", "hypertension", "joint_replacement"]
    relevant_conditions = {c for c in condition_keywords if c in canonical}
    hospital_name = (bill.hospital_name or "") if bill else ""

    # ── Filter in-memory cache — zero Neo4j round-trips at claim time ─────────
    result: dict = {}

    result["limits"] = _cache.get("limits", {})
    result["claim_requirements"] = _cache.get("claim_requirements", {})
    result["exclusions"] = _cache.get("exclusions", [])

    all_coverage = _cache.get("coverage", {})
    result["coverage"] = {k: v for k, v in all_coverage.items() if k in relevant_categories}

    all_wp = _cache.get("waiting_periods", {})
    specific_wp = {
        cond: days
        for cond, days in all_wp.get("specific", {}).items()
        if cond.lower() in relevant_conditions
    }
    if specific_wp:
        result["waiting_periods"] = specific_wp

    if hospital_name:
        result["network_hospitals"] = _cache.get("network_hospitals", [])

    return result
