# Cloud Cost Optimizer & Remediation Engine

Offline, API-first analyzer for exported AWS / Azure billing files. Detects orphaned and idle
resources via a rule engine and emits the exact CLI commands to decommission each one — without
ever connecting to a cloud account.

Full documentation lands in T9 (per `docs/PLAN.md`). For now:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
# → http://127.0.0.1:8000/health
pytest -q
```

See `docs/SPEC.md` for the full spec and `docs/PLAN.md` for the task breakdown.
