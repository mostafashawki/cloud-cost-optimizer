---
name: code-reviewer
description: "Use at the end of every task, before declaring it done, to review your own diff against the spec and the project's quality and safety bar. Produces a structured verdict (APPROVE / REQUEST CHANGES) with specific, actionable findings. Run after tests pass and ruff is clean."
---

# Code Reviewer

Review the diff for the current task as a critical senior reviewer would. Be specific and honest —
flag real problems, don't rubber-stamp. Walk the checklist, then give a verdict.

## Checklist
1. **Spec conformance.** Does the change satisfy *this task's* acceptance criteria in `docs/PLAN.md`
   and the relevant `SPEC.md` section? Anything missing or out of scope (work pulled forward from a
   later task)?
2. **Safety (critical for this repo).** No `boto3`/`botocore`/`azure-*` import; no
   `subprocess`/`os.system`; no network calls in detection. Destructive remediation commands are
   gated behind `confirm`. Remediation only *generates* strings.
3. **Domain correctness.** Detection matches `finops-domain`: no flagging of in-use/associated/
   running resources; cost taken from `UnblendedCost` not `UsageAmount`; savings math and fallback
   constants correct and documented; snapshots with a live source volume not flagged.
4. **Test adequacy.** Do the Required tests exist, and do they assert exact expected values from
   `sample/EXPECTED.md` rather than weak "> 0" checks? Is there a negative/clean-data case? Would the
   tests actually fail if the logic broke?
5. **Error handling.** Malformed uploads → 400/422 with a clear message, never 500. No bare excepts.
6. **Quality.** Full type hints; small pure functions where specified; named constants not magic
   numbers; no dead code, no `TODO`, no leftover debug prints; `ruff` clean; money rounded at output.
7. **Security/hygiene.** No secrets, no real account IDs, no PII in committed sample data; uploads
   size/shape validated.

## Output format
```
## Code Review — Task <id>
Verdict: APPROVE | REQUEST CHANGES
Blocking findings:
- [file:line] <issue> → <required fix>
Non-blocking suggestions:
- <nice-to-have>
Safety check: PASS | FAIL (<reason>)
```
If REQUEST CHANGES, apply the blocking fixes, re-run tests + ruff, and review again until APPROVE.
Only then report the task as done and update `prompts.md`.
