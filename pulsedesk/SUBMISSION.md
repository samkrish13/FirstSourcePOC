# PulseDesk — submission checklist

## Live demo / video

- [x] Streamlit Community Cloud: https://pulsedesk-firstsource.streamlit.app
- [x] GitHub: https://github.com/samkrish13/FirstSourcePOC
- [x] Deck slide 4 + READMEs use the live URL (rebuild: `python docs/build_summary_deck_pdf.py`)
- [ ] **Backup:** ≤3 min screen recording if live link fails (script: `docs/PulseDesk_Demo_Script.md` → **≤3 min panel path**)

## Brief compliance

- [x] ≥3 request types with **distinct** branches (6 golden: REQ-001…006)
- [x] Each branch: **response + route + follow-up + log**
- [x] README: setup + design notes + remediation table (`README.md`)
- [x] Sample input per branch (`data/sample_requests.json`) + output evidence (`screenshots/`, `../docs/sample_io/`)
- [x] 5-slide deck (`docs/PulseDesk_Summary.pdf` + repo copy `../docs/PulseDesk_Summary.pdf`)
- [x] Live demo URL documented; recording backup plan documented

## GitHub / Cloud

- [x] Repo: https://github.com/samkrish13/FirstSourcePOC
- [x] Streamlit Cloud main file: `pulsedesk/app.py`
- [ ] Confirm `.env` / `.streamlit/secrets.toml` / `*.db` **not** in git before each push
- [x] Secrets optional — heuristic mode works without them

## Demo accounts

| Login | Password | Role |
|---|---|---|
| `p.sharma` | `agent` | Agent |
| `r.mehta` | `lead` | Tech Lead |

**Panel path (≤3 min):** REQ-001 → REQ-002 → REQ-003 (billing / outage / escalation). See `docs/PulseDesk_Demo_Script.md`.
