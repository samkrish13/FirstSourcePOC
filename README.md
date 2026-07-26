# PulseDesk

**Live demo:** [https://pulsedesk-firstsource.streamlit.app](https://pulsedesk-firstsource.streamlit.app)  
**GitHub:** [github.com/samkrish13/FirstSourcePOC](https://github.com/samkrish13/FirstSourcePOC)

PulseDesk is a Streamlit workbench for telecom support ops. Agents pull requests from an inbox (or Gmail), run a playbook, and decide whether to release a reply or escalate to a tech lead.

**Full setup, remediation table, and deploy notes:** [`pulsedesk/README.md`](pulsedesk/README.md)  
**≤3 min demo path:** [`pulsedesk/docs/PulseDesk_Demo_Script.md`](pulsedesk/docs/PulseDesk_Demo_Script.md)  
**Submission checklist:** [`SUBMISSION.md`](SUBMISSION.md)

There’s also an unrelated stretch POC in [`signalforge/`](signalforge/) — ignore that for this brief.

---

## Quick start

```bash
git clone https://github.com/samkrish13/FirstSourcePOC.git
cd FirstSourcePOC/pulsedesk

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501).

**Demo accounts:** `p.sharma` / `agent` · `r.mehta` / `lead` (emails `@pulsedesk.demo` also work).

**Panel samples:** REQ-001 (billing) · REQ-002 (outage) · REQ-003 (escalation).

---

## What it does

1. **Process** — inbox, compose/upload, run playbook, release or escalate  
2. **Case Log** — SQLite audit of cases, actions, messages  
3. **Playbooks** — six remediation branches (brief requires ≥3)

Typical path: ingest → classify → remediate → human gate → persist.

Keep `.env`, `.streamlit/secrets.toml`, and `*.db` out of git.
