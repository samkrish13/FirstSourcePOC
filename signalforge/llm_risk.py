"""LLM risk adjustment and rationale (bounded ±15)."""
from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _openai_json(system: str, user: str) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return json.loads(resp.choices[0].message.content or "{}")


def heuristic_adjustment(
    features: dict[str, Any],
    alerts: list[dict[str, Any]],
    rule_score: int,
) -> dict[str, Any]:
    adjustment = 0
    red_flags: list[str] = []
    rationale_bits: list[str] = []

    texts = " ".join(a.get("text", "") for a in alerts).lower()
    if "mule" in texts or "watchlist" in texts:
        adjustment += 8
        red_flags.append("Consortium mule / watchlist language in external alert")
        rationale_bits.append("Unstructured alert reinforces mule-adjacency pattern.")
    if "false-positive" in texts or "benign" in texts or "confirmed purchase" in texts:
        adjustment -= 10
        rationale_bits.append("Unstructured note indicates likely false positive / confirmed benign.")
    if "itinerary may explain" in texts or "travel" in texts:
        adjustment -= 2
        rationale_bits.append("Travel context may explain geo anomaly; keep investigative, not punitive.")
    if features.get("new_device") and features.get("rapid_outbound_burst"):
        adjustment += 5
        red_flags.append("Device change immediately preceding outbound burst")
    if rule_score >= 70 and not red_flags:
        red_flags.append("Elevated rule score without mitigating narrative")

    adjustment = int(max(-15, min(15, adjustment)))
    actions = recommended_actions(rule_score + adjustment, features, red_flags)
    return {
        "adjustment": adjustment,
        "rationale": " ".join(rationale_bits) or "No material unstructured adjustment.",
        "red_flags": red_flags,
        "recommended_actions": actions,
        "mode": "heuristic",
    }


def recommended_actions(
    score: int,
    features: dict[str, Any],
    red_flags: list[str],
) -> list[str]:
    actions: list[str] = []
    if score >= 75:
        actions.extend(
            [
                "Place temporary debit hold / freeze outbound rails pending review",
                "Open RFI with customer on device change and beneficiaries",
                "Escalate to SAR triage if mule indicators confirm",
            ]
        )
    elif score >= 45:
        actions.extend(
            [
                "Queue enhanced due diligence review within 24h",
                "Verify travel / geo explanation with customer",
                "Monitor next 72h for repeat corridor activity",
            ]
        )
    else:
        actions.extend(
            [
                "Dismiss or suppress noisy alert with documented rationale",
                "Keep standard monitoring; no customer friction",
            ]
        )
    if features.get("failed_auth_spike"):
        actions.append("Force step-up authentication on next login")
    if not red_flags and score < 45:
        actions.append("Mark alert cluster as closed — benign")
    # dedupe preserve order
    seen = set()
    out = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def synthesize_risk(
    profile: dict[str, Any],
    features: dict[str, Any],
    factors: list[dict[str, Any]],
    rule: int,
    alerts: list[dict[str, Any]],
    txs_summary: list[dict[str, Any]],
) -> dict[str, Any]:
    if llm_available():
        try:
            result = _openai_json(
                system=(
                    "You are a financial crime analyst assistant. Return JSON with: "
                    "adjustment (int -15..15), rationale (string), red_flags (string array), "
                    "recommended_actions (string array, 2-4 items). "
                    "Do not invent transactions. Rules own the base score; you only adjust lightly."
                ),
                user=json.dumps(
                    {
                        "profile": profile,
                        "features": features,
                        "rule_score": rule,
                        "factors": factors,
                        "alerts": alerts,
                        "recent_transactions": txs_summary,
                    }
                ),
            )
            adj = int(result.get("adjustment", 0))
            adj = max(-15, min(15, adj))
            result["adjustment"] = adj
            result["mode"] = "llm"
            if not result.get("recommended_actions"):
                result["recommended_actions"] = recommended_actions(
                    rule + adj, features, result.get("red_flags") or []
                )
            result.setdefault("red_flags", [])
            result.setdefault("rationale", "")
            return result
        except Exception as exc:  # noqa: BLE001
            h = heuristic_adjustment(features, alerts, rule)
            h["rationale"] = f"LLM failed ({exc}). " + h["rationale"]
            return h
    return heuristic_adjustment(features, alerts, rule)
