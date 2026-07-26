"""Load and join multi-source risk inputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"


def ensure_data() -> None:
    required = [
        DATA / "customers.csv",
        DATA / "transactions.csv",
        DATA / "account_activity.csv",
        DATA / "external_alerts.json",
    ]
    if not all(p.exists() for p in required):
        import importlib.util

        gen_path = DATA / "generate_synthetic.py"
        spec = importlib.util.spec_from_file_location("generate_synthetic", gen_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        mod.generate()


def load_sources() -> dict[str, Any]:
    ensure_data()
    customers = pd.read_csv(DATA / "customers.csv")
    transactions = pd.read_csv(DATA / "transactions.csv")
    activity = pd.read_csv(DATA / "account_activity.csv")
    with open(DATA / "external_alerts.json", encoding="utf-8") as f:
        alerts = json.load(f)
    alerts_df = pd.DataFrame(alerts)
    return {
        "customers": customers,
        "transactions": transactions,
        "activity": activity,
        "alerts": alerts,
        "alerts_df": alerts_df,
    }


def customer_bundle(customer_id: str, sources: dict[str, Any] | None = None) -> dict[str, Any]:
    sources = sources or load_sources()
    cust = sources["customers"]
    row = cust.loc[cust["customer_id"] == customer_id]
    if row.empty:
        raise ValueError(f"Unknown customer_id: {customer_id}")
    profile = row.iloc[0].to_dict()
    txs = sources["transactions"]
    txs = txs.loc[txs["customer_id"] == customer_id].sort_values("ts")
    act = sources["activity"]
    act = act.loc[act["customer_id"] == customer_id].sort_values("ts")
    alerts = [a for a in sources["alerts"] if a["customer_id"] == customer_id]
    return {
        "profile": profile,
        "transactions": txs.reset_index(drop=True),
        "activity": act.reset_index(drop=True),
        "alerts": alerts,
    }
