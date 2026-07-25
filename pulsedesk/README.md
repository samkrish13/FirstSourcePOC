# PulseDesk

**Live demo:** [YOUR_STREAMLIT_URL_HERE](YOUR_STREAMLIT_URL_HERE)

Telecom BPO **incoming-request** workbench: classify → branch playbook → remediate → log.

---

## Problem

Contact-center / BPO agents manually triage every email. Intent is mixed (billing, outage, escalation, SIM/port, plan change, FAQ). Routing depends on individual judgment, so SLAs slip, replies stay generic, and there is little audit proof that the right playbook ran.

## Solution

**PulseDesk** is a Streamlit ops console that:

1. Takes an inbound request (compose, demo sample, or synced Gmail)
2. Classifies type, urgency, sentiment, entities, and confidence
3. Runs a **branch-specific playbook** (six categories)
4. Produces response draft + queue/ticket route + follow-up + SQLite audit log
5. Parks low-confidence work for human review (agent → escalate → tech lead)

Heuristic classifier works **without** an API key; optional OpenAI improves classification/drafts when configured.

## How it works (spine)

```text
Request in → Classify → Branch playbook → Response + Route + Follow-up → Log
```

| Stage | What happens |
|---|---|
| **Intake** | Work inbox / compose / Gmail sync / demo samples |
| **Classify** | Request type + confidence + entities |
| **Branch** | One of six remediation playbooks |
| **Act** | Draft, ticket/hold/notify/SLA, HITL release or escalate |
| **Log** | Case, actions, and messages in SQLite (Case Log) |

**Governance:** confidence **&lt; 0.65** → **Needs Review / On hold** before unsupervised release.

---

## Six-category remediation

| Branch | Key actions | Queue | Follow-up |
|---|---|---|---|
| **Billing dispute** | Provisional hold → Billing ticket → ack draft | Billing | 48h status |
| **Service outage** | Bulletin match → SLA reply **or** Network Ops ticket | Network Comms / Ops | SLA clock |
| **Complaint / escalation** | P1 Retention case → lead notify → recovery draft | Retention / Lead | Same-day callback |
| **SIM / port** | Identity checklist → Port/SIM ticket → status draft | Port/SIM | 24h status |
| **Plan change** | Eligibility → catalog quote → Care order | Care | Order confirmation |
| **General enquiry** | FAQ / self-serve → light ticket → close-or-route | General | Close or route |

Full contract: [`docs/REMEDIATION.md`](docs/REMEDIATION.md).

---

## Run locally

```bash
# Clone / download this repo, then:
cd pulsedesk

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

# Optional — app works without this (heuristic mode)
cp .env.example .env
# edit .env → OPENAI_API_KEY=...

streamlit run app.py
```

Open the local URL Streamlit prints (usually `http://localhost:8501`).

**Demo login (stub):**

| Account | Password | Role |
|---|---|---|
| `p.sharma` | `agent` | Agent |
| `r.mehta` | `lead` | Tech Lead |

Optional Gmail sync for `examplefirstsource@gmail.com`: copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` and set a Google App Password (see Stage notes). Not required for the sample demo.

---

## Which samples to click (panel demo)

In **Process**, expand **Load demo sample into form**, then **Run playbook**:

| Sample | Shows |
|---|---|
| **REQ-001** | Billing dispute — hold, Billing ticket, 48h follow-up |
| **REQ-002** | Service outage — bulletin match + SLA |
| **REQ-003** | Complaint / escalation — P1 + lead notify + callback |
| **REQ-004** | SIM / port — identity checklist + 24h status |
| **REQ-005** | Plan change — eligibility + Care order |
| **REQ-006** | General enquiry — FAQ + close-or-route |

Also try an **edge** sample (REQ-E0x) for the **Needs Review** confidence gate. Use **Coach: Compare** to show two branches side by side without writing Case Log.

Suggested live path: Agent runs REQ-001 → release or escalate → Sign out → Lead (`r.mehta`) resolves escalated queue.

---

## Project tree

```text
pulsedesk/
├── app.py                      # Streamlit entry
├── db.py                       # SQLite cases / actions / messages
├── requirements.txt
├── README.md
├── SUBMISSION.md
├── run_demo.py                 # Regenerate demo_outputs + sample_run_log
├── data/
│   ├── sample_requests.json    # Golden + edge samples
│   └── outage_bulletins.json
├── docs/
│   ├── PulseDesk_Summary.pdf   # 5-slide summary deck
│   └── REMEDIATION.md
├── integrations/
│   └── gmail_inbox.py          # Optional IMAP sync
├── pages/
│   ├── 0_Process.py            # Work inbox + run + spine
│   ├── 1_Case_Log.py
│   └── 2_Playbooks.py
├── screenshots/
│   ├── demo_outputs.json
│   ├── sample_run_log.txt
│   └── panel_review/           # UI panel stills
├── ui/
│   └── shell.py                # Chrome, tour, spine, HITL
└── workflows/                  # Classify + 6 branch playbooks
```

---

## Workflow design & governance

- **One spine, six playbooks** — every successful run must produce **response + route + follow-up + log** (see remediation contract).
- **Confidence gate** — below 0.65 → on hold / Needs Review; agent edits/releases or escalates with a reason; Tech Lead acknowledges, approves, or returns with a note.
- **Auditability** — Case Log and SQLite prove classification, actions, and drafts for ops review.
- **Simulation boundary** — outbound email release is labeled simulated until the mailbox channel is fully wired; Gmail sync is optional for inbound.

---

## Submission assets

| Asset | Location |
|---|---|
| 5-slide summary | [`docs/PulseDesk_Summary.pdf`](docs/PulseDesk_Summary.pdf) (also under repo [`../docs/PulseDesk_Summary.pdf`](../docs/PulseDesk_Summary.pdf)) |
| Screenshots / panels | [`screenshots/`](screenshots/) |
| All-branch demo log | [`screenshots/sample_run_log.txt`](screenshots/sample_run_log.txt) |
| Structured demo outputs | [`screenshots/demo_outputs.json`](screenshots/demo_outputs.json) |
| Checklist | [`SUBMISSION.md`](SUBMISSION.md) |

Regenerate demo artifacts:

```bash
source .venv/bin/activate
python run_demo.py
```

---

## Deploy (Stage 8) — GitHub + Streamlit Community Cloud

### A. Create a GitHub repo and push (from this machine)

**Important:** initialize git inside `FirstSourcePOC` (or only `pulsedesk`) — not your home directory.

**Option 1 — monorepo (recommended if you keep SignalForge too)**

```bash
cd /Users/sam/FirstSourcePOC
git init
git add pulsedesk docs/PulseDesk_Summary.pdf README.md SUBMISSION.md .gitignore
# optional: git add signalforge docs/SignalForge_Summary.pdf
git status   # confirm NO .env, secrets.toml, or *.db
git commit -m "$(cat <<'EOF'
Ship PulseDesk Stage 8 package for panel submission.

EOF
)"
gh repo create FirstSourcePOC --public --source=. --remote=origin --push
```

If `gh` is not logged in: `gh auth login`, then re-run the last line.  
Or create an empty repo on github.com and:

```bash
git remote add origin https://github.com/YOUR_USER/FirstSourcePOC.git
git branch -M main
git push -u origin main
```

**Option 2 — PulseDesk-only repo**

```bash
cd /Users/sam/FirstSourcePOC/pulsedesk
git init
git add .
git status   # confirm NO .env / secrets.toml / *.db
git commit -m "Ship PulseDesk for Streamlit Cloud"
gh repo create PulseDesk --public --source=. --remote=origin --push
```

### B. Deploy on Streamlit Community Cloud

1. Open [https://share.streamlit.io](https://share.streamlit.io) → **New app**
2. Connect the GitHub repo you just pushed
3. Settings:
   - **If monorepo:**  
     - Main file path: `pulsedesk/app.py`  
     - App URL subdomain: your choice (e.g. `pulsedesk-firstsource`)
   - **If PulseDesk-only repo:**  
     - Main file path: `app.py`
4. **Secrets (optional)** — Advanced settings → Secrets. App runs in **heuristic mode** with none.

```toml
# Optional — enables LLM classifier/drafts
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL = "gpt-4o-mini"

# Optional — Gmail Sync button
[gmail]
address = "examplefirstsource@gmail.com"
app_password = "xxxx xxxx xxxx xxxx"
```

5. Deploy → copy the live URL (e.g. `https://pulsedesk-firstsource.streamlit.app`)
6. Paste that URL back in chat — README + deck slide 4 will be updated

### C. ≤3 min recording backup (if live link fails on panel day)

Record locally: login as `p.sharma` / `agent` → Load **REQ-001** → Run playbook → show spine → Case Log → (optional) escalate → `r.mehta` / `lead` lead actions. Keep under 3 minutes. Store the file with the submission pack; link it from email if Cloud is down.
