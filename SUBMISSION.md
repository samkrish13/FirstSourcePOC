# Submission package checklist

Deliver to the specified email before the deadline.

## 1. Working demo — PulseDesk (primary)

**Live:** https://pulsedesk-firstsource.streamlit.app (Streamlit Community Cloud)  
**GitHub:** https://github.com/samkrish13/FirstSourcePOC  

**Local:**

```bash
cd pulsedesk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

**≤3 min demo path:** REQ-001 → REQ-002 → REQ-003 (see [`pulsedesk/docs/PulseDesk_Demo_Script.md`](pulsedesk/docs/PulseDesk_Demo_Script.md)).  
**Backup:** ≤3 minute screen recording if the live link fails.  
**Email draft:** [`docs/SUBMISSION_EMAIL.md`](docs/SUBMISSION_EMAIL.md)  
Headless proof: `cd pulsedesk && python run_demo.py` → `screenshots/sample_run_log.txt`.

Login stubs: `p.sharma` / `agent` · `r.mehta` / `lead`.

## 2. Five-slide deck

| POC | PDF |
|---|---|
| PulseDesk | [`docs/PulseDesk_Summary.pdf`](docs/PulseDesk_Summary.pdf) (copy also in `pulsedesk/docs/`) |

Rebuild: `python pulsedesk/docs/build_summary_deck_pdf.py`

## 3. Supporting assets

- README with setup + design + remediation: [`pulsedesk/README.md`](pulsedesk/README.md) ← **point judges here**
- Samples: `pulsedesk/data/sample_requests.json`
- Outputs: `pulsedesk/screenshots/`, `docs/sample_io/`
- Deploy steps: `pulsedesk/README.md` → Deploy
- Checklist: [`pulsedesk/SUBMISSION.md`](pulsedesk/SUBMISSION.md)
- Email draft: [`docs/SUBMISSION_EMAIL.md`](docs/SUBMISSION_EMAIL.md)

## 4. GitHub

Push `FirstSourcePOC` (monorepo) or `pulsedesk/` alone — see deploy section in `pulsedesk/README.md`.  
Never commit `.env`, `.streamlit/secrets.toml`, or `*.db`.
