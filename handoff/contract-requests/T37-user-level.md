# T37: skill level and display name on UserContext
What: two fields on `UserContext` (`backend/contracts/spec.py`), both defaulted so existing
fixtures, saved specs and saved memory still load:
```python
level: Literal["beginner", "intermediate", "expert"] = "intermediate"
"""How much the agent explains: wording of reasons, assumptions and questions, and part choices."""
name: str | None = None
"""Display name: shown in the sidebar; the agent addresses the user by it."""
```
`intermediate` is today's behaviour (the agent adds nothing to its prompts), so evals and API
callers that send no level are unchanged. The UI sends its own choice.
Why: T37 adapts the agent to the user's level, and T36's level selector and account name need real
values to send and show. `UserContext` forbids unknown fields, so neither can be sent today.
Affects:
- `make types` (frontend gets `level` and `name` on `UserContext`); B-web connects the placeholders (T40).
- `backend/memory/store.py` (T38's area): `PREFERENCES = ("budget_usd", "printer")` must add
  `"level", "name"`, or `PUT /memory` silently drops them and the sidebar name won't persist.
- T37: reads `user.level` / `user.name` in `backend/agent/`.
Workaround until decided: `backend/agent/` reads the fields with `getattr` and defaults
(`shortcut:` comment); tests use a local `UserContext` subclass with the two fields.
