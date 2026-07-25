# FirstSource POC — Dual AI Prototypes

| Prototype | Brief | Folder | Deck |
|---|---|---|---|
| **PulseDesk** *(primary)* | Incoming Request Processing Workflow | [`pulsedesk/`](pulsedesk/) | [`docs/PulseDesk_Summary.pdf`](docs/PulseDesk_Summary.pdf) |
| **SignalForge** *(stretch)* | Financial Risk Signal Aggregator | [`signalforge/`](signalforge/) | [`docs/SignalForge_Summary.pdf`](docs/SignalForge_Summary.pdf) |

**Live demo (PulseDesk):** [YOUR_STREAMLIT_URL_HERE](YOUR_STREAMLIT_URL_HERE) — replace after Streamlit Cloud deploy.

## PulseDesk quick start

```bash
cd pulsedesk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

No API key required (heuristic mode). Optional: copy `pulsedesk/.env.example` → `.env` and set `OPENAI_API_KEY`.

Full setup, remediation table, samples, and **GitHub + Streamlit Cloud deploy commands:** [`pulsedesk/README.md`](pulsedesk/README.md).

## Submission

- Checklist: [`pulsedesk/SUBMISSION.md`](pulsedesk/SUBMISSION.md)  
- Root checklist: [`SUBMISSION.md`](SUBMISSION.md)
