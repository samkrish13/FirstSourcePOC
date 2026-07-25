# PulseDesk — Remediation Contract

Spine for every successful run:

```text
Request in → Classification → Branch playbook → Response + Route + Follow-up + Log
```

Mandatory outcomes on **every** branch (brief compliance):

| Outcome | Meaning |
|---|---|
| **Response** | Customer-facing email/SMS draft appropriate to the branch |
| **Route** | Assign to the correct team/queue (ticket or queue handoff) |
| **Follow-up** | Scheduled callback, SLA clock, confirmation, or close/route disposition |
| **Log** | Persist case, actions, and messages to the audit store |

Confidence gate (enforced in later stages): confidence &lt; 0.65 → **Needs human review** before auto-remediation.

---

## 1. Billing Dispute (`billing_dispute`)

**Trigger examples**
- Duplicate / double charge on the same invoice
- Wrong amount, unexplained fee, refund request
- Payment posted but bill still shows unpaid

**Downstream steps (≥2)**
1. Place a **provisional hold** / dispute flag on the contested amount
2. Open a **Billing queue ticket** with invoice ID, amount, UTR/payment refs
3. Draft **acknowledgment email** with dispute reference and expected review window

**Target team / queue:** Billing

**Follow-up action:** Schedule **48-hour** status follow-up with the customer

**Response intent**
- Tone: calm, accountable, non-defensive
- Must include: account ID, disputed amount (if known), dispute/ticket reference, hold confirmation, 48h follow-up commitment

**Mandatory outcomes:** response ✓ · route (Billing) ✓ · follow-up (48h) ✓ · log ✓

---

## 2. Service Outage / Technical Fault (`service_outage`)

**Trigger examples**
- No data / no signal / intermittent voice in a named area
- “Is there a known outage?” with location context
- Service down after self-checks (reboot, airplane mode)

**Downstream steps (≥2)**
1. **Match** request location/service against `data/outage_bulletins.json`
2. **Matched path:** reply with ETA + workaround; log bulletin ID  
   **Unmatched path:** open **Network Ops** ticket for field/investigation
3. Start an **SLA clock** for update cadence

**Target team / queue:** Network Comms (matched bulletin) **or** Network Ops (unmatched)

**Follow-up action:** **SLA clock** — proactive update before ETA expires (or when ticket advances)

**Response intent**
- Tone: reassuring, concrete, ops-aware
- Must include: region acknowledged, matched bulletin ETA/workaround **or** Network Ops ticket ID, SLA update commitment

**Mandatory outcomes:** response ✓ · route (Network Comms / Network Ops) ✓ · follow-up (SLA) ✓ · log ✓

---

## 3. Complaint / Escalation (`complaint_escalation`)

**Trigger examples**
- Anger, cancel / port-out threats, TRAI / lawyer language
- Repeated unresolved tickets, “speak to a manager”
- Demands for compensation after failed promises

**Downstream steps (≥2)**
1. Open **P1 Retention** case (priority escalation)
2. **Notify Team Lead** / Retention queue with prior ticket IDs
3. Draft **recovery** response (apology + ownership + next contact)

**Target team / queue:** Retention / Team Lead

**Follow-up action:** **Same-day callback** task for Team Lead / Retention

**Response intent**
- Tone: empathetic, senior-owned, no template brush-off
- Must include: apology, acknowledgment of prior tickets (if cited), P1 case/reference, same-day callback commitment, clear owner

**Mandatory outcomes:** response ✓ · route (Retention / Team Lead) ✓ · follow-up (same-day callback) ✓ · log ✓

---

## 4. SIM / Port / Number Change (`sim_port`)

**Trigger examples**
- MNP port-in / port-out, UPC expiry pressure
- New SIM not activated, eKYC / identity pending
- Number change or SIM replacement status

**Downstream steps (≥2)**
1. Run **identity checklist** (KYC/eKYC, account match, SIM kit ID)
2. Open **Port/SIM queue** ticket with UPC / kit / number
3. Draft **status** reply (activation/port state + next step)

**Target team / queue:** Port/SIM

**Follow-up action:** **24-hour** port/activation status follow-up

**Response intent**
- Tone: precise, checklist-driven, time-sensitive where UPC expires soon
- Must include: number/account, identity checklist result summary, Port/SIM ticket ID, 24h status follow-up

**Mandatory outcomes:** response ✓ · route (Port/SIM) ✓ · follow-up (24h status) ✓ · log ✓

---

## 5. Plan Change / Upgrade-Downgrade (`plan_change`)

**Trigger examples**
- Want cheaper / unlimited / family plan
- Change effective next cycle; ask about fees and OTTs
- Eligibility / outstanding dues questions before change

**Downstream steps (≥2)**
1. **Eligibility check** (dues, contract lock, plan catalog fit)
2. Produce **catalog quote** (target plan, prorate / fee notes, benefit deltas)
3. Open **Care queue** order ticket and draft **confirmation** reply

**Target team / queue:** Care

**Follow-up action:** **Order confirmation** follow-up once change is scheduled/applied

**Response intent**
- Tone: clear, commercial, no surprise fees
- Must include: current vs target plan, eligibility result, key fee/OTT notes, Care order/ticket ID, confirmation follow-up

**Mandatory outcomes:** response ✓ · route (Care) ✓ · follow-up (order confirmation) ✓ · log ✓

---

## 6. General Enquiry (`general_enquiry`)

**Trigger examples**
- How-to questions (roaming, app settings, pack activation)
- FAQ-style asks that may be self-serve
- Informational only — no dispute, outage, or churn threat

**Downstream steps (≥2)**
1. Offer **FAQ / self-serve link** (or concise how-to steps)
2. Open light **General queue** tracking ticket for traceability
3. Set **close-or-route** disposition (close if answered; else route to specialist)

**Target team / queue:** General

**Follow-up action:** **Close-or-route** disposition — close if resolved via self-serve; otherwise route to the right specialist queue

**Response intent**
- Tone: helpful, concise, link-first
- Must include: direct answer or help-article path, tracking ticket ID, what happens next (closed vs routed)

**Mandatory outcomes:** response ✓ · route (General) ✓ · follow-up (close-or-route) ✓ · log ✓

---

## Edge cases (`ambiguous`)

Not a seventh playbook. Ambiguous / mixed-intent samples (see `data/sample_requests.json` → `edge_cases`) must either:

- Set **needs_review = true** and park in a human review lane, **or**
- Classify with lower confidence and still produce safe mandatory outcomes once a branch is chosen

Do not invent a generic “misc” remediation that skips route or follow-up.

---

## Sample ↔ branch map

| Sample ID | Branch |
|---|---|
| REQ-001 | billing_dispute |
| REQ-002 | service_outage |
| REQ-003 | complaint_escalation |
| REQ-004 | sim_port |
| REQ-005 | plan_change |
| REQ-006 | general_enquiry |
| REQ-E01–E03 | ambiguous (review / low-confidence) |
