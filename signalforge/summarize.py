"""Final analyst risk memo template."""
from __future__ import annotations

from typing import Any


def priority_label(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def build_memo(result: dict[str, Any]) -> str:
    profile = result["profile"]
    score = result["final_score"]
    priority = result["priority"]
    features = result["features"]
    llm = result["llm"]
    factors = result["factors"]

    top_factors = sorted(factors, key=lambda f: abs(f["points"]), reverse=True)[:5]
    factor_lines = "\n".join(
        f"  - {f['factor']} ({f['points']:+d}): {f['why']}" for f in top_factors
    )
    flags = llm.get("red_flags") or []
    flag_lines = "\n".join(f"  - {x}" for x in flags) if flags else "  - None material"
    actions = "\n".join(f"  {i}. {a}" for i, a in enumerate(llm.get("recommended_actions") or [], 1))

    return (
        f"RISK MEMO — {profile['customer_id']} ({profile.get('name')})\n"
        f"Priority: {priority} | Score: {score}/100 | Completeness: {features.get('data_completeness')}\n"
        f"KYC: {profile.get('kyc_tier')} | Tenure: {profile.get('tenure_months')} months | "
        f"Prior cases: {profile.get('prior_cases')}\n\n"
        f"Executive summary\n"
        f"  Rule base score {result['rule_score']} with LLM/heuristic adjustment "
        f"{llm.get('adjustment', 0):+d} → {score}. "
        f"{llm.get('rationale', '')}\n\n"
        f"Key drivers\n{factor_lines}\n\n"
        f"Red flags\n{flag_lines}\n\n"
        f"Recommended next actions\n{actions}\n"
    )


def aggregate_customer(bundle: dict[str, Any]) -> dict[str, Any]:
    from features import compute_features, rule_score
    from llm_risk import synthesize_risk

    features = compute_features(bundle)
    rule, factors = rule_score(features)
    txs = bundle["transactions"]
    txs_summary = txs.tail(8).to_dict(orient="records") if len(txs) else []
    llm = synthesize_risk(
        bundle["profile"],
        features,
        factors,
        rule,
        bundle["alerts"],
        txs_summary,
    )
    final = int(max(0, min(100, rule + int(llm.get("adjustment", 0)))))
    # soften by completeness
    if features.get("data_completeness", 1) < 1:
        # note only — do not silently change score much
        pass
    result = {
        "profile": bundle["profile"],
        "features": features,
        "factors": factors,
        "rule_score": rule,
        "llm": llm,
        "final_score": final,
        "priority": priority_label(final),
        "transactions": bundle["transactions"],
        "activity": bundle["activity"],
        "alerts": bundle["alerts"],
    }
    result["memo"] = build_memo(result)
    return result
