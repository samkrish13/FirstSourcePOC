"""SignalForge — Consolidated Financial Risk Desk."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

import db
from ingest import load_sources, customer_bundle
from llm_risk import llm_available
from summarize import aggregate_customer

st.set_page_config(
    page_title="SignalForge | Risk Desk",
    page_icon="🛡️",
    layout="wide",
)

PRIORITY_COLOR = {"HIGH": "#9B2226", "MEDIUM": "#BB3E03", "LOW": "#0B6E4F"}


def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
        html, body, [class*="css"] { font-family: 'Source Sans 3', sans-serif; }
        .block-container { padding-top: 1.1rem; max-width: 1280px; }
        .sf-hero {
            background: linear-gradient(120deg, #111827 0%, #1F2937 50%, #0F766E 130%);
            color: #F9FAFB; padding: 1.35rem 1.5rem; border-radius: 12px; margin-bottom: 1rem;
        }
        .sf-hero h1 { margin: 0; font-size: 1.75rem; }
        .sf-hero p { margin: 0.35rem 0 0; opacity: 0.88; }
        .sf-card {
            border: 1px solid #E5E7EB; border-radius: 10px; padding: 0.85rem 1rem; background: #FAFBFC;
        }
        .sf-score {
            font-family: 'IBM Plex Mono', monospace; font-size: 2.4rem; font-weight: 500; line-height: 1;
        }
        .sf-pill {
            display: inline-block; color: white; padding: 0.15rem 0.55rem; border-radius: 6px;
            font-size: 0.78rem; font-weight: 700; letter-spacing: 0.03em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_queue(sources) -> list[dict]:
    queue = []
    for _, row in sources["customers"].iterrows():
        cid = row["customer_id"]
        bundle = customer_bundle(cid, sources)
        result = aggregate_customer(bundle)
        queue.append(result)
    queue.sort(key=lambda r: r["final_score"], reverse=True)
    return queue


def main() -> None:
    inject_css()
    db.init_db()
    sources = load_sources()
    mode = "LLM + Rules" if llm_available() else "Rules + heuristic narrative"

    st.markdown(
        """
        <div class="sf-hero">
          <h1>SignalForge</h1>
          <p>Consolidated Risk Desk — fuse transactions, account activity, and external alerts into a prioritised, explainable view</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "queue" not in st.session_state:
        with st.spinner("Aggregating multi-source risk signals…"):
            st.session_state["queue"] = build_queue(sources)

    queue: list[dict] = st.session_state["queue"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Customers scored", len(queue))
    c2.metric("High priority", sum(1 for q in queue if q["priority"] == "HIGH"))
    c3.metric("Medium", sum(1 for q in queue if q["priority"] == "MEDIUM"))
    c4.metric("Engine", mode)

    left, right = st.columns([0.95, 1.55])

    with left:
        st.subheader("Prioritised queue")
        labels = [
            f"{q['priority']:6}  {q['final_score']:3}  {q['profile']['customer_id']}  {q['profile'].get('name')}"
            for q in queue
        ]
        pick = st.radio("Select case", labels, index=0, label_visibility="collapsed")
        idx = labels.index(pick)
        selected = queue[idx]
        if st.button("Recompute all", use_container_width=True):
            st.session_state.pop("queue", None)
            st.rerun()
        if st.button("Save analyst run", use_container_width=True):
            db.save_run(selected["profile"]["customer_id"], selected)
            st.success("Saved to SQLite audit log.")

        st.markdown("**Score distribution**")
        fig = px.bar(
            x=[q["profile"]["customer_id"] for q in queue],
            y=[q["final_score"] for q in queue],
            color=[q["priority"] for q in queue],
            color_discrete_map=PRIORITY_COLOR,
            labels={"x": "Customer", "y": "Score"},
        )
        fig.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=10), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        p = selected["profile"]
        color = PRIORITY_COLOR[selected["priority"]]
        st.markdown(
            f"### {p['customer_id']} — {p.get('name')} "
            f"<span class='sf-pill' style='background:{color}'>{selected['priority']}</span>",
            unsafe_allow_html=True,
        )
        a, b, c = st.columns(3)
        with a:
            st.markdown(
                f"<div class='sf-card'><div class='sf-score'>{selected['final_score']}</div>"
                f"<div>Final risk score</div></div>",
                unsafe_allow_html=True,
            )
        with b:
            st.markdown(
                f"<div class='sf-card'><div class='sf-score'>{selected['rule_score']}"
                f"<span style='font-size:1rem'>{selected['llm'].get('adjustment', 0):+d}</span></div>"
                f"<div>Rules + adjustment</div></div>",
                unsafe_allow_html=True,
            )
        with c:
            st.markdown(
                f"<div class='sf-card'><div class='sf-score'>"
                f"{selected['features'].get('data_completeness', 1):.0%}</div>"
                f"<div>Data completeness</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("#### Why this score")
        factors = selected["factors"]
        fig2 = px.bar(
            x=[f["points"] for f in factors],
            y=[f["factor"] for f in factors],
            orientation="h",
            labels={"x": "Points", "y": "Factor"},
            color=[f["points"] for f in factors],
            color_continuous_scale=["#0B6E4F", "#E5E7EB", "#9B2226"],
        )
        fig2.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
        for f in factors:
            st.caption(f"**{f['factor']} ({f['points']:+d})** — {f['why']}")

        st.markdown("#### Analyst risk memo")
        st.text_area("Memo", value=selected["memo"], height=260, label_visibility="collapsed")

        st.markdown("#### Recommended actions")
        for act in selected["llm"].get("recommended_actions") or []:
            st.checkbox(act, value=False, key=f"act-{p['customer_id']}-{act[:24]}")

        t1, t2, t3 = st.tabs(["Transactions", "Account activity", "External alerts"])
        with t1:
            st.dataframe(selected["transactions"], use_container_width=True)
        with t2:
            st.dataframe(selected["activity"], use_container_width=True)
        with t3:
            if selected["alerts"]:
                for al in selected["alerts"]:
                    st.markdown(f"**{al['alert_id']}** · {al['source']} · {al['severity']}")
                    st.write(al["text"])
            else:
                st.info("No external alerts for this customer.")

        with st.expander("Raw features / LLM payload"):
            st.json(
                {
                    "features": selected["features"],
                    "llm": selected["llm"],
                    "rationale": selected["llm"].get("rationale"),
                }
            )

    st.divider()
    st.subheader("Saved runs")
    runs = db.list_runs()
    if runs:
        st.dataframe(runs, use_container_width=True)
    else:
        st.caption("No saved runs yet.")


if __name__ == "__main__":
    main()
