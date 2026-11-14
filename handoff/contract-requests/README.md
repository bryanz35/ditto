# Contract requests

Contracts (`backend/contracts/`, `fixtures/`, `frontend/src/contracts/`) are frozen after Gate G0.
To ask for a change, add `<TASK>-<slug>.md` here on your own branch and tell your human:

```
# <TASK>: <one-line summary>
What: the exact field, type or signature change
Why: what you can't do with the current contract
Affects: tasks whose code or tests would change
Workaround until decided: what you're doing meanwhile
```

The Integrator answers within 30 minutes. Accepted changes land on `main` as their own commit,
bump `CONTRACT_VERSION`, and are announced in `handoff/MERGES.md`.
