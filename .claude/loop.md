Check the coordination board and act on it.

1. Run `python3 scripts/board.py next`.
2. If the ACTION is WAIT: reply in one line with what you're waiting for. If nothing changed since the
   last check, wait longer before the next one (up to 15 minutes); if things are moving, check again soon.
3. If the ACTION is DONE: tell me in one line what the board says to do next, then stop this loop.
4. Otherwise: do exactly what the action says, following CLAUDE.md and your task card. When that step is
   finished, run `python3 scripts/board.py next` again and keep going until it says WAIT or DONE.

Never edit the `coord` branch by hand, never merge into main unless you are the Integrator, and stop and
ask me if an action needs a decision that CLAUDE.md, your task card and the board don't answer.
