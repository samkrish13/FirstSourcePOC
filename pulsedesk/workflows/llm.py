"""LLM client with OpenAI JSON mode and offline heuristic fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

CONFIDENCE_REVIEW_THRESHOLD = 0.65

REQUEST_TYPES = (
    "billing_dispute",
    "service_outage",
    "complaint_escalation",
    "sim_port",
    "plan_change",
    "general_enquiry",
)

BRANCH_LABELS = {
    "billing_dispute": "Billing Dispute",
    "service_outage": "Service Outage / Technical Fault",
    "complaint_escalation": "Complaint / Escalation",
    "sim_port": "SIM / Port / Number Change",
    "plan_change": "Plan Change / Upgrade-Downgrade",
    "general_enquiry": "General Enquiry",
}


def llm_available() -> bool:
    return bool(_openai_api_key())


def _openai_api_key() -> str:
    """Env first, then Streamlit secrets — empty means heuristic mode."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st

        return str(st.secrets.get("OPENAI_API_KEY", "") or "").strip()
    except Exception:
        return ""


def _openai_json(system: str, user: str) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=_openai_api_key())
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
    content = resp.choices[0].message.content or "{}"
    return json.loads(content)


def _extract_account(text: str) -> str | None:
    m = re.search(r"ACC[- ]?\d{5,}", text, re.I)
    if not m:
        return None
    raw = m.group(0).upper().replace(" ", "")
    if not raw.startswith("ACC-"):
        raw = raw.replace("ACC", "ACC-", 1)
    return raw


def _extract_amount(text: str) -> str | None:
    m = re.search(r"₹\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", text)
    if m:
        return f"₹{m.group(1)}"
    m = re.search(r"\$\s?([0-9]+(?:\.[0-9]{2})?)", text)
    if m:
        return f"${m.group(1)}"
    m = re.search(r"\b([0-9]{3,5})\s*(?:rupees|rs\.?)\b", text, re.I)
    if m:
        return f"₹{m.group(1)}"
    return None


def _extract_invoice(text: str) -> str | None:
    # Require a separator + alnum so plain word "invoice" does not match
    m = re.search(r"\bINV[-_][A-Z0-9][-A-Z0-9]*\b", text, re.I)
    return m.group(0).upper() if m else None


def _extract_plan(text: str) -> str | None:
    patterns = [
        r"\bUnlimited\s+\d{3,4}\b",
        r"\bFamily\s+\d{3,4}\b",
        r"\b(?:plan|pack)\s+[A-Za-z]+\s+\d{3,4}\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(0)
    # Prefer "to X" target in plan-change phrasing
    m = re.search(r"\bto\s+((?:the\s+)?(?:Unlimited|Family)\s+\d{3,4})", text, re.I)
    if m:
        return re.sub(r"^the\s+", "", m.group(1), flags=re.I)
    return None


def _extract_location(text: str) -> str | None:
    places = [
        "Indiranagar",
        "Koramangala",
        "Andheri West",
        "Andheri",
        "Bangalore",
        "Bengaluru",
        "Mumbai",
        "Pune",
        "Hinjewadi",
        "Singapore",
    ]
    lower = text.lower()
    for place in places:
        if place.lower() in lower:
            return place
    m = re.search(r"\bpin\s+(\d{6})\b", text, re.I)
    if m:
        return f"PIN {m.group(1)}"
    return None


def _score_keywords(text: str, keywords: list[str], weight: float = 1.0) -> float:
    return sum(weight for kw in keywords if kw in text)


def _heuristic_classify(subject: str, body: str) -> dict[str, Any]:
    combined = f"{subject}\n{body}"
    text = combined.lower()

    scores: dict[str, float] = {t: 0.0 for t in REQUEST_TYPES}

    scores["billing_dispute"] += _score_keywords(
        text,
        [
            "charged twice",
            "double charge",
            "duplicate charge",
            "refund",
            "invoice",
            "billing",
            "disputed",
            "dispute",
            "wrong charge",
            "reverse the",
            "late fee",
            "payment",
            "utr",
            "bill of",
            "postpaid bill",
        ],
    )

    scores["service_outage"] += _score_keywords(
        text,
        [
            "outage",
            "no 4g",
            "no data",
            "no signal",
            "data has been",
            "completely down",
            "network",
            "known outage",
            "eta",
            "airplane mode",
            "voice calls are patchy",
            "won't load",
            "offline",
            "tower",
            "broadband",
        ],
    )

    scores["complaint_escalation"] += _score_keywords(
        text,
        [
            "trai",
            "lawyer",
            "legal",
            "final warning",
            "unacceptable",
            "team lead",
            "ombudsman",
            "compensation",
            "harassment",
            "port out to a competitor",
            "closing account",
            "cancel",
            "template reply",
            "three times",
            "no callback",
            "escalate",
            "manager",
            "supervisor",
        ],
        weight=1.5,
    )

    scores["sim_port"] += _score_keywords(
        text,
        [
            "mnp",
            "port-in",
            "port-out",
            "port in",
            "port out",
            "upc",
            "new sim",
            "sim not activated",
            "activation pending",
            "ekyc",
            "e-kyc",
            "identity verification",
            "sim kit",
            "port status",
            "number change",
        ],
        weight=1.4,
    )

    scores["plan_change"] += _score_keywords(
        text,
        [
            "downgrade",
            "upgrade",
            "change my plan",
            "plan from",
            "to the family",
            "next billing cycle",
            "prorated",
            "early-termination",
            "early termination",
            "eligible",
            "otts",
            "want unlimited",
            "cheaper plan",
            "family 499",
            "plan change",
        ],
        weight=1.3,
    )

    scores["general_enquiry"] += _score_keywords(
        text,
        [
            "how do i",
            "how to",
            "need to know",
            "what packs",
            "help article",
            "international roaming",
            "roaming",
            "activate (app",
            "self-serve",
            "would be fine if",
            "travelling to",
            "trip to",
        ],
    )

    # Strong override cues — escalation / port / plan / how-to beat mixed billing language
    if any(
        cue in text
        for cue in (
            "trai",
            "final warning",
            "lawyer",
            "team lead",
            "port out to a competitor",
            "closing account if",
        )
    ):
        scores["complaint_escalation"] += 5.0

    if any(cue in text for cue in ("mnp", "upc", "port-in", "port-out", "activation pending")):
        scores["sim_port"] += 4.0

    if any(
        cue in text
        for cue in ("downgrade from", "upgrade from", "change my plan", "next billing cycle")
    ):
        scores["plan_change"] += 4.0

    if text.strip().startswith("how do i") or "how do i " in text or subject.lower().startswith(
        "how do i"
    ):
        scores["general_enquiry"] += 4.0

    if "known outage" in text or "no 4g" in text or "no data since" in text:
        scores["service_outage"] += 3.0

    if "charged twice" in text or "duplicate charge" in text:
        scores["billing_dispute"] += 3.0

    request_type = max(scores, key=scores.get)
    raw = scores[request_type]
    ranked = sorted(scores.values(), reverse=True)
    second = ranked[1] if len(ranked) > 1 else 0.0
    margin = raw - second

    # How many categories look "live"? Mixed intent → review lane
    live_categories = sum(1 for v in scores.values() if v >= 2.0)
    vague = bool(
        re.search(
            r"something is wrong|need help with my account|please fix asap|look into both",
            text,
            re.I,
        )
    )
    mixed_markers = bool(
        re.search(
            r"\band also\b|look into both|port my number and|and cancel the disputed",
            text,
            re.I,
        )
    )

    if raw <= 0:
        request_type = "general_enquiry"
        confidence = 0.4
    else:
        confidence = min(0.97, 0.55 + raw * 0.06 + margin * 0.04)
        # Ambiguous if top two are close
        if margin < 1.5 and raw < 6:
            confidence = min(confidence, 0.62)
        # Strong single-intent winners stay high-confidence
        clear_winner = margin >= 5.0 or raw >= 8.0
        if not clear_winner:
            if live_categories >= 3 or (live_categories >= 2 and margin < 4.0):
                confidence = min(confidence, 0.58)
            if vague or mixed_markers:
                confidence = min(confidence, 0.55)
            if vague and raw < 4:
                confidence = min(confidence, 0.45)
        elif mixed_markers and live_categories >= 3:
            # Explicit multi-intent even with a loud top score (e.g. port+dispute+churn)
            confidence = min(confidence, 0.55)
        elif vague:
            confidence = min(confidence, 0.55)

    sentiment = "neutral"
    if any(w in text for w in ("unacceptable", "harassment", "furious", "lawyer", "final warning")):
        sentiment = "very_negative"
    elif any(w in text for w in ("frustrated", "asap", "still wasn't", "blocked", "urgent")):
        sentiment = "negative"
    elif any(w in text for w in ("thank", "please", "hi,")):
        sentiment = "neutral"

    urgency = "medium"
    if request_type == "complaint_escalation" or "today" in text or "expires tomorrow" in text:
        urgency = "critical"
    elif request_type == "service_outage" or "urgent" in text or "asap" in text:
        urgency = "high"
    elif request_type in ("general_enquiry", "plan_change"):
        urgency = "low" if request_type == "general_enquiry" else "medium"

    entities = {
        "account": _extract_account(combined),
        "amount": _extract_amount(combined),
        "location": _extract_location(combined),
        "plan": _extract_plan(combined),
        "invoice": _extract_invoice(combined),
    }

    rationale = f"Heuristic scores={scores}; selected={request_type}"
    if live_categories >= 2 or vague:
        rationale += (
            f"; ambiguity_flags={{live:{live_categories},vague:{vague},"
            f"mixed:{mixed_markers},margin:{round(margin,2)}}}"
        )

    return {
        "request_type": request_type,
        "urgency": urgency,
        "sentiment": sentiment,
        "confidence": round(float(confidence), 2),
        "entities": entities,
        "rationale": rationale,
        "mode": "heuristic",
    }


def _normalize_classification(result: dict[str, Any], *, mode: str) -> dict[str, Any]:
    request_type = result.get("request_type", "general_enquiry")
    if request_type not in REQUEST_TYPES:
        request_type = "general_enquiry"

    entities_in = result.get("entities") or {}
    entities = {
        "account": entities_in.get("account"),
        "amount": entities_in.get("amount"),
        "location": entities_in.get("location"),
        "plan": entities_in.get("plan"),
        "invoice": entities_in.get("invoice"),
    }

    try:
        confidence = float(result.get("confidence", 0.7))
    except (TypeError, ValueError):
        confidence = 0.7
    confidence = max(0.0, min(1.0, confidence))

    return {
        "request_type": request_type,
        "urgency": result.get("urgency") or "medium",
        "sentiment": result.get("sentiment") or "neutral",
        "confidence": round(confidence, 2),
        "entities": entities,
        "rationale": result.get("rationale") or "",
        "mode": mode,
    }


def classify_request(subject: str, body: str) -> dict[str, Any]:
    if llm_available():
        try:
            result = _openai_json(
                system=(
                    "You are a telecom BPO intake classifier for PulseDesk. Return JSON with keys: "
                    "request_type (billing_dispute|service_outage|complaint_escalation|"
                    "sim_port|plan_change|general_enquiry), "
                    "urgency (low|medium|high|critical), "
                    "sentiment (positive|neutral|negative|very_negative), "
                    "confidence (0-1 float), "
                    "entities (object with account, amount, location, plan, invoice — null if unknown), "
                    "rationale (short string). "
                    "Prefer complaint_escalation when TRAI/lawyer/cancel threats dominate. "
                    "Prefer sim_port for MNP/UPC/SIM activation. "
                    "Prefer plan_change for upgrade/downgrade requests. "
                    "Prefer general_enquiry for how-to / roaming FAQ questions."
                ),
                user=f"Subject: {subject}\n\nBody:\n{body}",
            )
            return _normalize_classification(result, mode="llm")
        except Exception as exc:  # noqa: BLE001
            fallback = _heuristic_classify(subject, body)
            fallback["rationale"] = (
                f"LLM failed ({exc}); used heuristic. " + fallback["rationale"]
            )
            return fallback
    return _heuristic_classify(subject, body)


def draft_response(request_type: str, context: dict[str, Any]) -> str:
    if llm_available():
        try:
            result = _openai_json(
                system=(
                    "You draft concise, professional telecom customer emails for an Indian BPO. "
                    "Return JSON: {\"email_body\": \"...\"}. No subject line. "
                    "Be empathetic, specific to the remediation context, under 180 words."
                ),
                user=json.dumps({"request_type": request_type, "context": context}),
            )
            body = result.get("email_body") or result.get("body")
            if body:
                return str(body).strip()
        except Exception:
            pass
    return _heuristic_draft(request_type, context)


def _heuristic_draft(request_type: str, context: dict[str, Any]) -> str:
    account = context.get("account") or "your account"
    name = "Customer"

    if request_type == "billing_dispute":
        amount = context.get("amount") or "the disputed amount"
        ticket = context.get("ticket_id", "BIL-XXXX")
        return (
            f"Dear {name},\n\n"
            f"Thank you for contacting us about the billing concern on {account}. "
            f"We have opened ticket {ticket} and placed a provisional hold while Billing "
            f"reviews {amount}. You will receive an update within 48 hours.\n\n"
            f"Regards,\nPulseDesk Billing Care"
        )

    if request_type == "service_outage":
        bulletin = context.get("bulletin_id")
        eta = context.get("eta_hours")
        workaround = context.get("workaround") or "Please reboot your device and retry."
        if bulletin:
            return (
                f"Dear {name},\n\n"
                f"We matched an active network event ({bulletin}) for {account}. "
                f"Estimated restoration is about {eta} hours. Workaround: {workaround}\n\n"
                f"We will notify you when service is restored.\n\n"
                f"Regards,\nPulseDesk Network Care"
            )
        ticket = context.get("ticket_id", "NET-XXXX")
        return (
            f"Dear {name},\n\n"
            f"We could not match your issue to a known outage, so ticket {ticket} has been "
            f"routed to Network Operations for {account}. A specialist will investigate shortly.\n\n"
            f"Regards,\nPulseDesk Network Care"
        )

    if request_type == "complaint_escalation":
        ticket = context.get("ticket_id", "RET-XXXX")
        return (
            f"Dear {name},\n\n"
            f"I am sorry for the experience you described. We have raised Priority-1 retention "
            f"case {ticket} for {account}. A Team Lead will call you today.\n\n"
            f"Regards,\nPulseDesk Customer Care Leadership"
        )

    if request_type == "sim_port":
        ticket = context.get("ticket_id", "SIM-XXXX")
        return (
            f"Dear {name},\n\n"
            f"We have logged Port/SIM ticket {ticket} for {account} and completed an identity "
            f"checklist review. We will update you on activation/port status within 24 hours.\n\n"
            f"Regards,\nPulseDesk Port & SIM Desk"
        )

    if request_type == "plan_change":
        ticket = context.get("ticket_id", "CARE-XXXX")
        target = context.get("target_plan") or "your requested plan"
        return (
            f"Dear {name},\n\n"
            f"We have checked eligibility for {account} and opened Care order {ticket} for the "
            f"change to {target}. You will receive order confirmation shortly.\n\n"
            f"Regards,\nPulseDesk Care"
        )

    link = context.get("faq_link") or "https://help.pulsedesk.example/roaming"
    ticket = context.get("ticket_id", "GEN-XXXX")
    return (
        f"Dear {name},\n\n"
        f"Thanks for your enquiry on {account}. Please see: {link}. "
        f"Tracking reference: {ticket}. Reply if you still need an agent.\n\n"
        f"Regards,\nPulseDesk Support"
    )
