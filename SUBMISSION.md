# Submission package checklist

Deliver to the specified email before the deadline.

## 1. Working demo — PulseDesk (primary)

**Live:** YOUR_STREAMLIT_URL_HERE (Streamlit Community Cloud)  
**Local:**

```bash
cd pulsedesk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Demo: `REQ-001`, `REQ-002`, `REQ-003` (and optionally 004–006) — distinct remediation branches.  
**Backup:** ≤3 minute screen recording if the live link fails (script in `pulsedesk/README.md`).  
Headless proof: `python run_demo.py` → `pulsedesk/screenshots/sample_run_log.txt`.

Login stubs: `p.sharma` / `agent` · `r.mehta` / `lead`.

## 2. Five-slide deck

| POC | PDF |
|---|---|
| PulseDesk | [`docs/PulseDesk_Summary.pdf`](docs/PulseDesk_Summary.pdf) |

## 3. Supporting assets

- README with setup + design + remediation: [`pulsedesk/README.md`](pulsedesk/README.md)
- Samples: `pulsedesk/data/sample_requests.json`
- Outputs: `pulsedesk/screenshots/demo_outputs.json`, `sample_run_log.txt`, panel JPGs
- Deploy steps: `pulsedesk/README.md` → Deploy (Stage 8)
- Checklist: [`pulsedesk/SUBMISSION.md`](pulsedesk/SUBMISSION.md)

## 4. GitHub

Push `FirstSourcePOC` (monorepo) or `pulsedesk/` alone — see deploy section in `pulsedesk/README.md`.  
Never commit `.env`, `.streamlit/secrets.toml`, or `*.db`.
