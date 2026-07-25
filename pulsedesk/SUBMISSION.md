# PulseDesk — submission checklist (Stage 8)

## Live demo / video

- [ ] Streamlit Community Cloud URL live
- [ ] Paste URL into chat so README + deck slide 4 can be updated (replace `YOUR_STREAMLIT_URL_HERE`)
- [ ] **Backup:** ≤3 min screen recording if live link fails (see README Deploy §C)

## Brief compliance

- [x] ≥3 request types with **distinct** branches (6 golden: REQ-001…006)
- [x] Each branch: **response + route + follow-up + log** (`docs/REMEDIATION.md` + `run_demo.py` gate)
- [x] README: setup + design notes + remediation table
- [x] Sample input per branch (`data/sample_requests.json`) + output evidence (`screenshots/`)
- [x] 5-slide deck (`docs/PulseDesk_Summary.pdf`)
- [x] Live-link placeholder + recording backup plan documented

## GitHub / Cloud

- [ ] Repo created and pushed (see README Deploy)
- [ ] `.env` / `.streamlit/secrets.toml` / `*.db` **not** in git
- [ ] Streamlit Cloud main file: `pulsedesk/app.py` (monorepo) or `app.py` (app-only)
- [ ] Secrets optional — heuristic mode works without them

## Demo accounts

| Login | Password | Role |
|---|---|---|
| `p.sharma` | `agent` | Agent |
| `r.mehta` | `lead` | Tech Lead |

Panel path: REQ-001 → Run → Case Log; optionally escalate → lead login.
