# Submission Checklist - Amazon Nova Hackathon

## Deadlines

- Submission deadline: **March 16, 2026, 5:00 PM PT**
- Feedback deadline: **March 18, 2026, 5:00 PM PT**
- AWS credit request deadline: **March 13, 2026, 5:00 PM PT**

## Technical checks

- [ ] `POST /v1/sessions` works
- [ ] `POST /v1/chat` works
- [ ] `POST /v1/runs/{session_id}/resume` works
- [ ] `GET /v1/recommendations/{session_id}` returns score breakdown and risk flags
- [ ] `GET /v1/sessions/{session_id}` returns checkpoint trace
- [ ] Test suite passes (`pytest -q`)

## Safety and policy checks

- [ ] UI executor enforces `stop_before_pay=true`
- [ ] Autofill is only attempted when `consentAutofill=true`
- [ ] Blocked automation path returns graceful recommendation (`WAIT`/`AVOID`) with risk flags

## Demo artifacts

- [ ] 3-minute demo video script aligned to runbook
- [ ] Public or shareable code access ready for judging
- [ ] README/runbook updated for local and docker usage
- [ ] Judge script includes one normal path and one blocked-automation path

## Final packaging

- [ ] Submission text explains Nova usage (planner/review/visual/executor/decision)
- [ ] Mention trust scoring dimensions and explainability output
- [ ] Confirm no payment action is executed in any flow

