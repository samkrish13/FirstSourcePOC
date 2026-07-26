"""Deterministic risk feature engineering and rule score."""
from __future__ import annotations

from typing import Any

import pandas as pd

HIGH_RISK_COUNTRIES = {"NG", "GH", "MM", "KP"}
HIGH_RISK_MCC = {"crypto", "p2p", "cash"}


def compute_features(bundle: dict[str, Any]) -> dict[str, Any]:
    profile = bundle["profile"]
    txs: pd.DataFrame = bundle["transactions"]
    activity: pd.DataFrame = bundle["activity"]
    alerts = bundle["alerts"]

    features: dict[str, Any] = {
        "tx_count_7d": int(len(txs)),
        "tx_sum_7d": float(txs["amount"].sum()) if len(txs) else 0.0,
        "max_tx": float(txs["amount"].max()) if len(txs) else 0.0,
        "high_risk_country_txs": 0,
        "high_risk_mcc_txs": 0,
        "rapid_outbound_burst": False,
        "new_device": False,
        "failed_auth_spike": False,
        "watchlist_hit": False,
        "geo_velocity_alert": False,
        "tenure_months": int(profile.get("tenure_months", 0)),
        "prior_cases": int(profile.get("prior_cases", 0)),
        "kyc_tier": profile.get("kyc_tier"),
        "data_completeness": 1.0,
    }

    if len(txs):
        features["high_risk_country_txs"] = int(txs["country"].isin(HIGH_RISK_COUNTRIES).sum())
        features["high_risk_mcc_txs"] = int(txs["mcc_group"].isin(HIGH_RISK_MCC).sum())
        # burst: 3+ outbound-like txs within short window (same day hour cluster)
        app_txs = txs[txs["channel"].isin(["app", "atm", "transfer"])]
        if len(app_txs) >= 3:
            features["rapid_outbound_burst"] = True

    if len(activity):
        features["new_device"] = bool(activity["device_change"].astype(bool).any())
        features["failed_auth_spike"] = bool((activity["failed_auth_count_24h"] >= 5).any())

    for a in alerts:
        src = (a.get("source") or "").lower()
        if "watchlist" in src:
            features["watchlist_hit"] = True
        if "geo" in src or "velocity" in src:
            features["geo_velocity_alert"] = True

    # completeness: penalize if no activity or no alerts context
    missing = 0
    if len(activity) == 0:
        missing += 1
    if len(txs) == 0:
        missing += 1
    features["data_completeness"] = round(1.0 - 0.15 * missing, 2)
    return features


def rule_score(features: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Return base score 0-100 and factor breakdown."""
    factors: list[dict[str, Any]] = []
    score = 10  # baseline monitoring

    def add(name: str, pts: int, why: str) -> None:
        nonlocal score
        score += pts
        factors.append({"factor": name, "points": pts, "why": why})

    if features["watchlist_hit"]:
        add("watchlist_hit", 30, "External watchlist / consortium adjacency")
    if features["rapid_outbound_burst"]:
        add("rapid_outbound_burst", 18, "Multiple outbound transfers in a tight window")
    if features["new_device"] and features["max_tx"] >= 1000:
        add("new_device_large_transfer", 16, "New device combined with large transfer")
    elif features["new_device"]:
        add("new_device", 8, "Recent device change")
    if features["failed_auth_spike"]:
        add("failed_auth_spike", 10, "Failed authentication spike in 24h")
    if features["high_risk_country_txs"] >= 2:
        add("high_risk_corridor", 14, "Multiple txs involving higher-risk corridors")
    elif features["high_risk_country_txs"] == 1:
        add("high_risk_corridor", 7, "Transaction involving higher-risk corridor")
    if features["high_risk_mcc_txs"] >= 2:
        add("high_risk_mcc", 12, "Crypto/P2P/cash activity concentration")
    elif features["high_risk_mcc_txs"] == 1:
        add("high_risk_mcc", 6, "Elevated MCC group present")
    if features["geo_velocity_alert"] and not features["watchlist_hit"]:
        add("geo_velocity", 32, "Geo-velocity / travel anomaly alert")
    if features["tenure_months"] < 6:
        add("thin_file", 6, "Short tenure / thin behavioural history")
    if features["prior_cases"] >= 2:
        add("repeat_cases", 5, "Prior risk cases on file")
    # Mild uplift when spend jumps into a new country without mule markers
    if features["geo_velocity_alert"] and features["tx_sum_7d"] >= 800:
        add("elevated_travel_spend", 12, "Material spend during travel window")

    # benign dampener for low-noise profiles
    if (
        not features["watchlist_hit"]
        and not features["rapid_outbound_burst"]
        and not features["geo_velocity_alert"]
        and features["high_risk_mcc_txs"] == 0
        and features["tx_sum_7d"] < 500
    ):
        add("benign_pattern", -8, "Low value, domestic-like activity pattern")

    score = int(max(0, min(100, score)))
    return score, factors
