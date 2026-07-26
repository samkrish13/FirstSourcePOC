"""Generate reproducible synthetic multi-source risk data."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
SEED = 42


def generate(seed: int = SEED) -> dict[str, Path]:
    rng = np.random.default_rng(seed)
    ROOT.mkdir(parents=True, exist_ok=True)

    customers = pd.DataFrame(
        [
            {
                "customer_id": "CUS-1001",
                "name": "Asha Verma",
                "kyc_tier": "standard",
                "tenure_months": 4,
                "prior_cases": 0,
                "segment": "retail",
                "demo_tier": "high",
            },
            {
                "customer_id": "CUS-1002",
                "name": "Ben Okonkwo",
                "kyc_tier": "enhanced",
                "tenure_months": 36,
                "prior_cases": 1,
                "segment": "retail",
                "demo_tier": "medium",
            },
            {
                "customer_id": "CUS-1003",
                "name": "Chloe Tan",
                "kyc_tier": "standard",
                "tenure_months": 18,
                "prior_cases": 0,
                "segment": "retail",
                "demo_tier": "low",
            },
            {
                "customer_id": "CUS-1004",
                "name": "Dev Patel",
                "kyc_tier": "standard",
                "tenure_months": 8,
                "prior_cases": 2,
                "segment": "sme",
                "demo_tier": "medium",
            },
            {
                "customer_id": "CUS-1005",
                "name": "Elena Rossi",
                "kyc_tier": "enhanced",
                "tenure_months": 48,
                "prior_cases": 0,
                "segment": "retail",
                "demo_tier": "low",
            },
        ]
    )

    # Transactions — crafted patterns per showcase customer
    tx_rows = [
        # CUS-1001 high: rapid outbound + high-risk corridor
        ("CUS-1001", "2026-07-20T09:10:00Z", 50.0, "CAFE_LOCAL", "IN", "pos", "retail"),
        ("CUS-1001", "2026-07-22T02:11:00Z", 2400.0, "CRYPTO_RAMP", "NG", "app", "crypto"),
        ("CUS-1001", "2026-07-22T02:18:00Z", 3100.0, "P2P_WALLET", "NG", "app", "p2p"),
        ("CUS-1001", "2026-07-22T02:25:00Z", 2800.0, "P2P_WALLET", "GH", "app", "p2p"),
        ("CUS-1001", "2026-07-22T03:01:00Z", 1500.0, "ATM_WITHDRAW", "NG", "atm", "cash"),
        # CUS-1002 medium: travel geo anomaly, otherwise normal
        ("CUS-1002", "2026-07-18T12:00:00Z", 85.0, "GROCERIES", "GB", "pos", "retail"),
        ("CUS-1002", "2026-07-19T08:30:00Z", 42.0, "TRANSIT", "GB", "pos", "travel"),
        ("CUS-1002", "2026-07-21T19:40:00Z", 620.0, "HOTEL_DUBAI", "AE", "pos", "travel"),
        ("CUS-1002", "2026-07-22T10:15:00Z", 95.0, "RESTAURANT", "AE", "pos", "retail"),
        ("CUS-1002", "2026-07-22T16:00:00Z", 210.0, "ELECTRONICS", "AE", "pos", "retail"),
        # CUS-1003 low: benign + noisy alert explained
        ("CUS-1003", "2026-07-20T11:00:00Z", 25.0, "COFFEE", "SG", "pos", "retail"),
        ("CUS-1003", "2026-07-21T14:20:00Z", 120.0, "ONLINE_SHOP", "SG", "web", "retail"),
        ("CUS-1003", "2026-07-22T09:05:00Z", 60.0, "PHARMACY", "SG", "pos", "retail"),
        # extras
        ("CUS-1004", "2026-07-21T07:00:00Z", 900.0, "SUPPLIER_PAY", "IN", "transfer", "b2b"),
        ("CUS-1004", "2026-07-22T07:05:00Z", 1100.0, "SUPPLIER_PAY", "IN", "transfer", "b2b"),
        ("CUS-1005", "2026-07-19T18:00:00Z", 45.0, "STREAMING", "IT", "web", "retail"),
        ("CUS-1005", "2026-07-21T12:00:00Z", 200.0, "AIRLINE", "IT", "web", "travel"),
    ]
    # sprinkle a few random small txs
    for cid in ["CUS-1003", "CUS-1005"]:
        for i in range(3):
            tx_rows.append(
                (
                    cid,
                    f"2026-07-{15+i:02d}T10:{10+i:02d}:00Z",
                    float(rng.integers(10, 80)),
                    "MISC_RETAIL",
                    "SG" if cid == "CUS-1003" else "IT",
                    "pos",
                    "retail",
                )
            )

    transactions = pd.DataFrame(
        tx_rows,
        columns=[
            "customer_id",
            "ts",
            "amount",
            "merchant",
            "country",
            "channel",
            "mcc_group",
        ],
    )

    activity = pd.DataFrame(
        [
            {
                "customer_id": "CUS-1001",
                "ts": "2026-07-22T02:05:00Z",
                "event": "new_device_login",
                "geo": "Lagos, NG",
                "device_change": True,
                "failed_auth_count_24h": 6,
            },
            {
                "customer_id": "CUS-1001",
                "ts": "2026-07-22T02:09:00Z",
                "event": "password_reset",
                "geo": "Lagos, NG",
                "device_change": True,
                "failed_auth_count_24h": 6,
            },
            {
                "customer_id": "CUS-1002",
                "ts": "2026-07-21T15:00:00Z",
                "event": "login",
                "geo": "Dubai, AE",
                "device_change": False,
                "failed_auth_count_24h": 0,
            },
            {
                "customer_id": "CUS-1002",
                "ts": "2026-07-20T09:00:00Z",
                "event": "login",
                "geo": "London, GB",
                "device_change": False,
                "failed_auth_count_24h": 1,
            },
            {
                "customer_id": "CUS-1003",
                "ts": "2026-07-21T08:00:00Z",
                "event": "login",
                "geo": "Singapore, SG",
                "device_change": False,
                "failed_auth_count_24h": 0,
            },
            {
                "customer_id": "CUS-1004",
                "ts": "2026-07-22T06:50:00Z",
                "event": "login",
                "geo": "Mumbai, IN",
                "device_change": True,
                "failed_auth_count_24h": 2,
            },
            {
                "customer_id": "CUS-1005",
                "ts": "2026-07-21T11:00:00Z",
                "event": "login",
                "geo": "Milan, IT",
                "device_change": False,
                "failed_auth_count_24h": 0,
            },
        ]
    )

    alerts = [
        {
            "alert_id": "ALT-9001",
            "customer_id": "CUS-1001",
            "source": "watchlist_fuzzy",
            "severity": "high",
            "ts": "2026-07-22T03:10:00Z",
            "text": (
                "Fuzzy watchlist adjacency: beneficiary wallet tag overlaps a consortium "
                "mule cluster (score 0.81). Rapid outbound sequence post device change."
            ),
        },
        {
            "alert_id": "ALT-9002",
            "customer_id": "CUS-1002",
            "source": "geo_velocity",
            "severity": "medium",
            "ts": "2026-07-21T20:00:00Z",
            "text": (
                "Impossible-travel style alert: GB login morning, AE card presentment evening. "
                "Customer itinerary may explain; no cash-out pattern observed."
            ),
        },
        {
            "alert_id": "ALT-9003",
            "customer_id": "CUS-1003",
            "source": "fraud_consortium",
            "severity": "low",
            "ts": "2026-07-21T16:00:00Z",
            "text": (
                "Noisy MCC alert on ONLINE_SHOP. Merchant was previously false-positive prone. "
                "Customer confirmed purchase via in-app chat; treat as benign unless new signals."
            ),
        },
        {
            "alert_id": "ALT-9004",
            "customer_id": "CUS-1004",
            "source": "velocity",
            "severity": "medium",
            "ts": "2026-07-22T07:10:00Z",
            "text": "Two supplier transfers in 24h above peer baseline for SME segment.",
        },
    ]

    paths = {}
    customers.to_csv(ROOT / "customers.csv", index=False)
    transactions.to_csv(ROOT / "transactions.csv", index=False)
    activity.to_csv(ROOT / "account_activity.csv", index=False)
    with open(ROOT / "external_alerts.json", "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)
    paths["customers"] = ROOT / "customers.csv"
    paths["transactions"] = ROOT / "transactions.csv"
    paths["activity"] = ROOT / "account_activity.csv"
    paths["alerts"] = ROOT / "external_alerts.json"
    meta = {"seed": seed, "customers": len(customers), "transactions": len(transactions)}
    with open(ROOT / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return paths


if __name__ == "__main__":
    out = generate()
    print("Generated:", {k: str(v) for k, v in out.items()})
