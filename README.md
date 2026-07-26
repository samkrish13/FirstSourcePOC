# PulseDesk

PulseDesk is a Streamlit workbench for telecom support ops. Agents pull requests from an inbox (or Gmail), run a playbook, and decide whether to release a reply or escalate to a tech lead.

It lives in this monorepo under [`pulsedesk/`](pulsedesk/). There’s also an unrelated stretch POC in [`signalforge/`](signalforge/) — ignore that unless you care about it.

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

**Demo accounts**

| | Email | Password |
|---|---|---|
| Agent | `p.sharma@pulsedesk.demo` | `agent` |
| Tech lead | `r.mehta@pulsedesk.demo` | `lead` |

Usernames (`p.sharma` / `r.mehta`) work too.

---

## What it does

1. **Process** — work the inbox, compose or upload a request, run a playbook, release or escalate.
2. **Case Log** — history of cases, statuses, and actions.
3. **Playbooks** — the remediation branches (billing, outage, escalation, and so on).

Optional Gmail sync: connect a mailbox in **Process → Connect / manage mailboxes**, paste a Google App Password, then **Sync**. Cases land in the workbench like any other inbox item.

OpenAI is optional. Without `OPENAI_API_KEY`, classification falls back to heuristics and the app still runs.

```bash
cp .env.example .env
# OPENAI_API_KEY=...
```

---

## Project layout

```
pulsedesk/
  app.py              entrypoint
  pages/              Process, Case Log, Playbooks
  ui/shell.py         login, chrome, result UI
  workflows/          classify + branch remediation
  integrations/       Gmail IMAP sync
  db.py               SQLite
  data/               sample requests
```

Typical path: ingest → classify → remediate → human gate (hold / release / escalate) → persist.

---

## Notes

- **Claim** only assigns ownership. It does not run a playbook.
- HOLD means a human should review before anything goes out.
- SLA / supervisor banners in the UI are simulated for the demo.
- Keep `.env`, `.streamlit/secrets.toml`, and `*.db` out of git.

Python 3.10+; Streamlit 1.46+ (see `pulsedesk/requirements.txt`).

---

## Deploy

On Streamlit Community Cloud, point the app at `pulsedesk/app.py` and add any secrets in the dashboard.
