# PulseDesk — demo script

**Live:** https://pulsedesk-firstsource.streamlit.app  
**GitHub:** https://github.com/samkrish13/FirstSourcePOC  
**Local:** `cd pulsedesk && streamlit run app.py`

| Role | Login | Password |
|---|---|---|
| Agent | `p.sharma@pulsedesk.demo` | `agent` |
| Tech Lead | `r.mehta@pulsedesk.demo` | `lead` |

---

## ≤3 min panel path (use this for the brief)

Shows **three distinct branches** end-to-end. Say the one-liner once, then click.

***“AI classifies the request, runs a typed multi-step playbook — draft, route, follow-up, log — and a human can release or escalate.”***

| Clock | Action | Say |
|---|---|---|
| 0:00–0:20 | Open live URL → login `p.sharma` / `agent` | “Agent desk — Process inbox + workbench.” |
| 0:20–1:10 | **Load demo sample → REQ-001 → Run playbook** | “Billing dispute — hold, Billing ticket, 48h follow-up, ack draft.” |
| 1:10–1:50 | **REQ-002 → Run playbook** | “Outage — different queue and SLA path, not a generic reply.” |
| 1:50–2:30 | **REQ-003 → Run playbook** | “Escalation — P1 Retention, lead notify, same-day callback.” |
| 2:30–2:55 | Open **Case Log**, pick one case | “Audit trail — classification, actions, draft persisted.” |
| 2:55–3:00 | Optional: open **Playbooks** | “Six branches total; we showed three.” |

**Recording backup:** same clicks locally if Cloud is down. Skip lead login unless you have extra time.

---

## Extended ~5 min script (optional)

**Bold italic** = say out loud. Plain bullets = clicks.

### 0. Frame the problem (30 sec)

Open the live URL (or localhost). Stay on the login screen for one beat.

***“Telecom BPO desks get mixed inbound mail all day — billing, outages, escalations, SIM/port, plan changes, FAQs. Today agents read each one and invent the next steps. That’s slow, inconsistent, and hard to audit.”***

***“PulseDesk is a 3-day POC that proves AI can classify the request, run the right multi-step playbook, and leave a Case Log — with a human gate when confidence is low.”***

### 1. Agent login → Process desk (40 sec)

1. Sign in as **Agent** — `p.sharma` / `agent`
2. Land on **Process**
3. Point at sidebar: Process · Case Log · Playbooks · profile

***“Left rail is the work inbox — Mine, Unassigned, All. Right side is the case workbench. Same metaphor as a real ops console.”***

### 2. Golden path — REQ-001 billing (90 sec)

1. Expand **Load demo sample** → **REQ-001** → **Load sample**
2. Show Subject + body (duplicate charge / refund)
3. Click **Run playbook**
4. Walk the spine: classification → entities → branch → timeline → draft → queue/48h → checklist

***“That’s the product: classify → branch playbook → remediate → log.”***

### 3. Second + third branch (40–80 sec)

1. Load **REQ-002** (outage) → **Run playbook** — Network / SLA
2. Load **REQ-003** (escalation) → **Run playbook** — Retention / callback

***“Different ops paths — different tickets, different SLAs.”***

### 4–7. Optional deeper beats

HITL escalate (REQ-E01), Case Log Replay, Tech Lead (`r.mehta` / `lead`), Playbooks table — only if time remains after the three-branch path.

---

## Backup if Cloud fails

Record ≤3 min locally with the **≤3 min panel path** above. Samples work offline; OpenAI key optional (heuristic mode).

## Don’t derail unless asked

- Deep Gmail connect / App Password walkthrough  
- OpenAI vs heuristic details  
- SignalForge stretch POC  
- CSS / Streamlit internals  
