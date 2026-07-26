# Screenshots & demo artifacts

Generated / curated for Stage 7 panel submission.

## UI panels

| File | Intent |
|---|---|
| `01_process_inbox.jpg` | Process — work inbox / intake |
| `02_result_spine.jpg` | Result spine after Run playbook |
| `03_case_log.jpg` | Case Log audit view |
| `04_playbooks.jpg` | Playbooks overview |

Refresh captures later from a live session if the UI chrome changes materially.

## Branch evidence (all 6 + edges)

| File | Contents |
|---|---|
| `demo_outputs.json` | Structured results for REQ-001…006 + edge cases |
| `sample_run_log.txt` | Human-readable run log with drafts |

Regenerate:

```bash
cd pulsedesk
source .venv/bin/activate
python run_demo.py
```

Expect: `GATE PASSED: all 6 golden branches + ambiguous review lane.`
