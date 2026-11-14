# Runbook: running the agents, step by step

This is the "what do I type, and when" guide for teammates new to running several Claude Code agents at
once. `BUILD_PLAN.md` explains *why* the work is split this way; this file tells you *what to do*.
Every prompt below is ready to copy and paste.

**The short version:** a shared board tracks every task, review, sign-off and merge. Each agent asks
the board what to do next, does it, and keeps checking while it waits. You start sessions, approve plans
and permissions, answer questions, and do the few human-only tasks.

---

## 1. Six ideas you need first

1. **A session is one Claude Code conversation in one terminal tab.** You start one by opening a
   terminal, moving into a folder (`cd`), and typing `claude`. It works only inside that folder.
2. **A worktree is a second copy of the repo in its own folder, on its own branch.** Ours sit next to
   the main folder, e.g. `../ditto-T10-validators`. Several agents can edit "the same repo" at once without
   touching each other's files. Our script creates them; you never need raw git commands.
3. **One task = one worktree = one session.** Never run two sessions in the same folder. When a task
   is merged, close its tab and start the next task in a *fresh* worktree.
4. **There are four kinds of agent.** All are ordinary Claude Code sessions; the prompt gives each its role:

   | Role | How many | What it does | Where it runs |
   | --- | --- | --- | --- |
   | **Integrator** | 1 (Person A) | Builds the shared foundation, merges finished work into `main`, rules on interface changes | The main repo folder |
   | **Builder** | many | Builds one task from its card | That task's worktree |
   | **QA** | 1 (Person D) | Writes integration and end-to-end tests from the interfaces | Its own worktree |
   | **Reviewer** | 1 (Person B) | Reviews every finished branch; never writes features | `../ditto-review` |

5. **The board is the switchboard.** `handoff/tasks.json` says who depends on whom and who consumes
   whose output. The live state sits on a git branch called `coord` that no one edits by hand. Every
   agent runs `python3 scripts/board.py next` and gets exactly one next action. Reviews, sign-offs,
   merges and "rebase now" notices reach the right agent without you passing messages.
6. **`/loop` keeps an agent checking the board while it waits.** After you approve an agent's plan,
   type `/loop` in its tab (no arguments). Each time the session goes idle, Claude Code wakes it up
   again, at an interval it picks (between a minute and an hour), to run `.claude/loop.md`: check the
   board and act. The session must stay open; press Esc to stop the loop.

---

## 2. Who runs what

| Person | Sessions they run (in order over the weekend) | Also responsible for |
| --- | --- | --- |
| **A** | Integrator (all weekend) · B-agent: T13 → T33 → T37 | Contract review at G0, hardware check (H0) |
| **B** | B-cad: T11 → T25 → T34 · B-parts: T18 → T26 · Reviewer (all weekend) | Measuring parts (H1), printing (H4) |
| **C** | B-api: T14 → T22 → T39 · B-fw: T12 → T23 → T31 · B-validate: T10 → T21 | Showcase device choice (H2) and wiring |
| **D** | B-web: T15 → T24 → T36 → T40 · B-bom: T16 → T17 → T38 · QA: T19 → T30 | Makerspace interview (H3), demo video, Devpost |

Nobody runs more than three sessions at once. If your team is smaller, merge columns and follow the
priority order in section 5.

---

## 3. Before the event (every person, ~30 minutes)

- [ ] Claude Code installed and logged in: `claude` opens a session.
- [ ] `git`, `gh` (GitHub CLI, then `gh auth login`), `uv`, Node 20+, `ffmpeg`, PlatformIO Core (`pio`).
- [ ] Python 3.12+.
- [ ] Push access to the team's GitHub repo (the board lives there too, on the `coord` branch).
- [ ] Person A only: a `.env` file with the API keys (model provider, Nexar, Wokwi). It's never committed;
      the worktree script links it into every worktree.
- [ ] Learn four keys: **Shift+Tab** cycles the permission mode (watch the status bar), **Esc** stops
      Claude mid-step (and stops `/loop`), `/clear` starts a clean conversation in the same tab, and
      `claude --continue` reopens the last conversation in a folder.

**Permissions, in plain terms:** when Claude asks to run something, allow edits inside your worktree and
commands like `make`, `uv`, `pytest`, `npm`, `pio`, `python3 scripts/board.py`, `git add`, `git commit`,
`git rebase`, `git push` of the task's own branch, `gh pr create`.
**Don't allow** `git push` to `main` (except the Integrator), deleting files outside the worktree, or
editing another worktree. Never start a session with permission checks turned off.

---

## 4. Hour 0–4: the foundation (Person A drives; everyone else prepares)

### Step 1 · Person A: set up the repo (5 min)

```bash
git clone <your-repo-url> p2d && cd p2d
# unzip the handoff bundle here: CLAUDE.md, .claude/, handoff/, docs/, scripts/
cp /path/to/.env .env
git add -A && git commit -m "docs: add build plan, runbook and board" && git push
claude
```

The first time you run `claude` in a folder, it asks whether you trust it. Say yes.

### Step 2 · Person A: start the Integrator

Paste the **Integrator kickoff** prompt from the appendix. Read the plan it proposes and reply
`Approved, go ahead` (or correct it). It builds T00 and T01, then stops at Gate G0.

### Meanwhile · everyone else (hour 0–3)

- **Person A or B (H0, by hour 2):** find out whether parts and a 3D printer are available. Fill in
  `handoff/HARDWARE.md` and send it to Person A to commit.
- **Person C (H2, by hour 4):** choose the showcase device with the team (library parts that Wokwi
  supports, calls an AI model through our backend). Write two or three sentences describing it; you'll
  paste them into the T31 prompt later.
- **Person D:** ask organizers and sponsors the open questions (track limits, printer, Physical AI rule).
- **Everyone:** read `CLAUDE.md` and your own task cards in `BUILD_PLAN.md` section 5.

### Step 3 · Gate G0: review the contracts (Person B, hour ~3)

Everything built in parallel depends on these files, so a second pair of eyes is worth 20 minutes. In a
**new** terminal tab, in the main folder:

```bash
cd p2d && git pull && claude --permission-mode plan
```

Plan mode means this session can read but not edit. Paste:

```text
You are reviewing the shared contracts before ten agents start building against them in parallel.
Read CLAUDE.md, handoff/BUILD_PLAN.md (sections 0, 5 for T01, and every task card's "Build" list),
handoff/tasks.json and docs/PROJECT_PLAN.md. Then read everything in backend/contracts/, fixtures/,
backend/tools/ (stubs) and frontend/src/contracts/.
Check: every function signature a task card needs exists and matches; every field the cards mention
exists (rev, Placement, Layout, dims_source, wokwi_type, event stages and statuses, data field); fixtures
validate; nothing a task needs is missing. List problems as a numbered list, most serious first.
Only flag things that would block or mislead a builder, not style.
```

Person B pastes the list into the Integrator's tab:

```text
Contract review findings: <paste the numbered list>.
Fix the ones you agree with, explain any you disagree with, rerun `make lint test` and the contract
tests, commit and push. Then tell me G0 is complete.
```

Type `/exit` in the reviewer tab (the real Reviewer starts in step 5).

### Step 4 · Person A: start the board and create the worktrees (hour ~4)

In the Integrator's tab:

```text
G0 is approved. Run `python3 scripts/board.py init`, then `python3 scripts/board.py done T00` and
`python3 scripts/board.py done T01`, then `python3 scripts/board.py status` and show me the output.
```

Then in a plain terminal in the main folder (not inside Claude):

```bash
git pull
scripts/setup_worktrees.sh wave1
python3 scripts/board.py status
```

The status table should show T10–T19 as "human: start it". Tell the team "worktrees are ready", then type
`/loop` in the Integrator's tab so it starts merging and answering contract requests on its own.

---

## 5. Hour 4: start Wave 1 (staggered)

Start sessions **in this order, about 3 minutes apart**, so you don't hit rate limits all at once and the
longest tasks start first. For each one:

1. Open a new terminal tab and name it after the task (e.g. `T13 agent`).
2. `cd ../ditto-<TASK>-<slug>` (the folder name is in the table), then `claude --permission-mode plan`.
3. Paste that task's **kickoff prompt from the appendix**.
4. Claude reads the files, checks the board and proposes a plan. Compare it with the task card: right
   files, right tests, nothing outside the card. Reply `Approved, go ahead` (Claude Code leaves plan
   mode when you approve) or tell it what to change.
5. Once it's working, type `/loop`. It will keep building, then submit, then react to the board by itself.

| Order | Who | Task | Folder | Role |
| --- | --- | --- | --- | --- |
| 1 | A | T13 agent orchestration | `../ditto-T13-agent` | Builder |
| 2 | B | T11 layout + enclosure | `../ditto-T11-cad` | Builder |
| 3 | C | T14 API + run engine | `../ditto-T14-api` | Builder |
| 4 | C | T12 firmware toolchain | `../ditto-T12-firmware` | Builder |
| 5 | D | T15 frontend shell | `../ditto-T15-web` | Builder |
| 6 | C | T10 validators | `../ditto-T10-validators` | Builder |
| 7 | D | T19 QA test suite | `../ditto-T19-qa` | QA |
| 8 | D | T16 pricing + memory | `../ditto-T16-bom` | Builder |
| 9 | B | T18 parts library | `../ditto-T18-parts` | Builder |
| 10 | B | Reviewer | `../ditto-review` | Reviewer |

The Reviewer starts with plain `claude` (no plan mode), the **Reviewer kickoff** prompt from the
appendix, then `/loop`.

---

## 6. Your job during the weekend

The board moves work between agents. Here's what happens without you:

| When this happens | The board gives this action | To |
| --- | --- | --- |
| A builder runs `board.py submit` | `REVIEW <task>` | Reviewer |
| The Reviewer requests changes | `FIX_REVIEW` with the numbered notes | That builder |
| The Reviewer approves | `SIGNOFF <task>` | Each consumer agent named in `tasks.json` |
| A consumer reports a failure | `FIX_REVIEW` with the consumer's notes | That builder |
| Approved and all sign-offs in, at the same commit | `MERGE <task>` | Integrator |
| A task is merged | `REBASE` to agents that consume it; `QA_UPDATE` to QA; `DONE` to its builder | Those agents |
| A builder files a contract request | `DECIDE_CONTRACT` | Integrator |
| The Integrator lands a contract change with `announce --rebase` | `REBASE` | Every active builder |
| A builder pushes new commits after approval | The approval stops counting; the task goes back to `REVIEW` | Reviewer |

What's left for you:

1. **Every ~30 minutes:** `python3 scripts/board.py status` from any folder. It shows each task's
   state, review, sign-offs, who acts next, what's ready to start, and recent activity.
2. **Watch your tabs** for permission prompts and questions. A loop can't approve a permission for you.
3. **When an agent reports DONE:** close its tab and start the next task it names. The status table's
   "Ready to start now" list gives the exact command, for example:

   ```bash
   git pull
   scripts/setup_worktrees.sh add T21 cross-checks
   scripts/setup_worktrees.sh remove T10        # the finished one
   ```

   Then a new tab: `cd ../ditto-T21-cross-checks`, `claude --permission-mode plan`, paste the kickoff
   prompt, approve the plan, `/loop`.
4. **Human tasks and human sign-offs:** run `python3 scripts/board.py --as human next`. It lists the
   H-tasks that are ready (mark one finished with `board.py done H0 --as human`). It also lists
   sign-offs only a human can give: the T18 datasheet spot-check and T33's docs, recorded with
   `board.py signoff T18 ok --as human --notes "checked 3 parts"`.

### Problems and how to handle them

| Situation | What to do |
| --- | --- |
| Agent asks to change a shared contract or edit a file it doesn't own | Tell it: `File a contract request as CLAUDE.md describes (write the file, push, board.py request) and keep going with the current contract.` The Integrator picks it up from the board. |
| Agent is going in circles (same error twice) | Press Esc, then: `Stop. In five bullets: what you tried, what's failing, your best guess at the cause, and the smallest next step. Don't change any files yet.` Decide with it, or ask the owner of the file involved. |
| Agent is waiting on another task for a long time | `python3 scripts/board.py status`: the "NEXT STEP BY" column shows who's holding it up. Go nudge that tab. |
| Session feels slow or forgetful (long conversation) | `/compact Keep the task card, the plan, files changed and test commands.` If still bad: `/clear`, then paste the resume prompt below. |
| Returning to a session after a break, or after `/clear` | `You are the <ROLE> for task <TASK>. Read CLAUDE.md, your card in handoff/BUILD_PLAN.md, your notes in handoff/status/<TASK>.md and git log -10, then run python3 scripts/board.py next and do what it says. Tell me where you're picking up before you change anything.` Then `/loop` again (a loop doesn't survive `/clear` or a restart). |
| A session crashed or the tab closed | `cd` into the same worktree, `claude --continue`, then `/loop`. |
| `board.py` says it can't write ("after 10 tries") | Usually no network. Check `git fetch` works, then rerun the same command. |
| Rate-limited or out of capacity | Press Esc in the lowest-priority sessions (order in section 5, bottom first). Resume them later with the resume prompt. |
| Hardware mode changes mid-weekend | Person A updates `handoff/HARDWARE.md` on main. The board reads it from main, so dependencies and optional tasks update by themselves; tell the Integrator to run `board.py announce "hardware mode is now X" --rebase`. |
| You want to see exactly what an agent will be told | `python3 scripts/board.py --as <agent> next`, e.g. `--as B-web`. |

---

## 7. Later tasks and gates

You don't have to work out when a task can start: the "Ready to start now" list in
`board.py status` shows it, and an agent finishing its task tells you whether its next task is ready.
For reference, the order is:

| Agent | Tasks in order | Person |
| --- | --- | --- |
| Integrator | T00 → T01 → T20 (integration, in the main folder after `/clear`) | A |
| B-agent | T13 → T33 → T37 | A |
| B-cad | T11 → T25 → T34 (optional) | B |
| B-parts | T18 → T26 | B |
| Reviewer | reviews all weekend → T35 (release check, after `/clear`) | B |
| B-api | T14 → T22 → T39 | C |
| B-fw | T12 → T23 → T31 (needs the H2 device description) | C |
| B-validate | T10 → T21 | C |
| B-web | T15 → T24 → T36 → T40 | D |
| B-bom | T16 → T17 → T38 | D |
| QA | T19 → T30 (needs example prompt 3 from H3) | D |

**Gates** (Person A announces each one in the team chat):

- **G1, hour 18:** when the Integrator finishes T20, ask QA: `Run tests/e2e/test_plant_monitor.py with the real runner (make test-live for that file only) and report pass/fail with the output.`
- **G2, hour 24:** ask QA to run `tests/e2e/test_edits.py` the same way; humans confirm the hardware check for your mode (section 0 of BUILD_PLAN.md).
- **G3, hour 32 (feature freeze):** after T30's report, nobody starts new features. Person A runs `python3 scripts/board.py announce "feature freeze: bug fixes only"` in the Integrator tab.

---

## 8. Hour 32–35: release

1. Person A, Integrator tab: `Feature freeze. Merge only bug fixes from now on. Show me python3 scripts/board.py status.`
2. Person B, Reviewer tab: `/clear`, then paste the T35 kickoff prompt from the appendix.
3. Everyone: rehearse the demo for your hardware mode, plus the cached-run fallback (`P2D_RUNNER=replay:<dir> make dev`).
4. Submit on Devpost by hour 35.

---

## Appendix: kickoff prompts

Paste the block for your task into a fresh session started in that task's folder with
`claude --permission-mode plan` (Reviewer: plain `claude`). After you approve the plan, type `/loop`.

### Integrator kickoff (T00, T01)

Main folder · Person A

```text
You are the Integrator (I) for this hackathon project.
Read CLAUDE.md, then all of handoff/BUILD_PLAN.md, handoff/tasks.json and docs/PROJECT_PLAN.md.
Your job now is tasks T00 then T01, working directly on main. (The board doesn't exist yet; you'll
create it at Gate G0.)
Before writing code, give me a short plan for T00 and T01: the files you'll create, in what order, and
how you'll prove the G0 checks in section 1 pass. Wait for my approval.
After approval: do T00, commit; do T01, commit. Run `make lint test` after each. Keep scripts/board.py,
scripts/setup_worktrees.sh, handoff/tasks.json and .claude/loop.md exactly as they are.
Stop at Gate G0 and give me: the list of contract files, anything you weren't sure about, and the exact
commands that prove G0. Don't start any other task.
After G0, your loop is: run `python3 scripts/board.py next` and do what it says (MERGE, DECIDE_CONTRACT,
WORK on T20 when it's ready), then run it again.
```

### Reviewer kickoff

Folder `../ditto-review` · Person B

```text
You are the Reviewer (R) for this project. You never write feature code.
Read CLAUDE.md (especially the coordination board section) and section 6 of handoff/BUILD_PLAN.md.
Your loop: run `python3 scripts/board.py next`. For each REVIEW action, check out the branch detached in
this folder as the action says, run the checks in section 6 against that task's card in section 5, and
record your verdict with `python3 scripts/board.py review <TASK> approve --notes "..."` or
`... changes --notes-file <file>` (a numbered list, most serious first, only things that affect
correctness, the card's acceptance criteria, or the rules in CLAUDE.md). If the repo is on GitHub, also
post the verdict with `gh pr review`. Then run `next` again.
Start now: run `python3 scripts/board.py next` and tell me what it says.
```

### T10 · Spec validators

Folder `../ditto-T10-validators` · branch `feat/T10-validators` · agent B-validate · consumer sign-off: B-agent (T13)

```text
You are the B-validate agent, a Builder, for task T10 (Spec validators), working in this git worktree on branch feat/T10-validators.
1. Read CLAUDE.md (especially the coordination board section), the T10 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T10.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T10-validators`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Board facts (reserved, input-only, strapping, ADC2 pins) come only from the board YAML. Start from the invalid fixtures in fixtures/specs/: one test per error code.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T11 · Layout and enclosure

Folder `../ditto-T11-cad` · branch `feat/T11-cad` · agent B-cad · consumer sign-off: B-web (T15) and B-validate (T21)

```text
You are the B-cad agent, a Builder, for task T11 (Layout and enclosure), working in this git worktree on branch feat/T11-cad.
1. Read CLAUDE.md (especially the coordination board section), the T11 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T11.md, commit.
5. Build in small commits. Run `make lint test` (and `make test-slow`, which your card lists) as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T11-cad`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Dimensions are provisional until measured; use the `generic` printer profile until handoff/HARDWARE.md names a printer. Determinism matters: same spec, byte-identical layout and manifest.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T12 · Firmware toolchain

Folder `../ditto-T12-firmware` · branch `feat/T12-firmware` · agent B-fw · consumer sign-off: B-agent (T13)

```text
You are the B-fw agent, a Builder, for task T12 (Firmware toolchain), working in this git worktree on branch feat/T12-firmware.
1. Read CLAUDE.md (especially the coordination board section), the T12 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T12.md, commit.
5. Build in small commits. Run `make lint test` (and `make test-slow`, which your card lists) as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T12-firmware`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: First run one PlatformIO build of the golden plant monitor so the toolchain downloads, and note how long it took in your status file. Remember the P2D_READY line and the lint rules.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T13 · Agent orchestration

Folder `../ditto-T13-agent` · branch `feat/T13-agent` · agent B-agent · consumer sign-off: B-api (T14)

```text
You are the B-agent agent, a Builder, for task T13 (Agent orchestration), working in this git worktree on branch feat/T13-agent.
1. Read CLAUDE.md (especially the coordination board section), the T13 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T13.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T13-agent`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Before planning, check the installed deepagents version and read its docs; write the exact API you'll use (create_deep_agent arguments, sub-agent keys, planning, interrupts, checkpointer) into your status file. Read "Using deepagents" in docs/PROJECT_PLAN.md. Use fake_toolbox() for every unit test; only `make test-live` calls a real model. The runner is `AgentRunner(toolbox, model, run_stages)` with `run()`, `edit()` and `answer()`, and does model work only (read the docstring of backend/contracts/runner.py). Check work through the injected StageRunner (a fake one in tests); never import backend/runtime/.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T14 · API and run engine

Folder `../ditto-T14-api` · branch `feat/T14-api` · agent B-api · consumer sign-off: B-web (T15)

```text
You are the B-api agent, a Builder, for task T14 (API and run engine), working in this git worktree on branch feat/T14-api.
1. Read CLAUDE.md (especially the coordination board section), the T14 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T14.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T14-api`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Do deps.py, the replay runner and `backend/runtime/stages.py: run_stages` (the StageRunner that T13 calls) first, so B-web can develop against P2D_RUNNER=fake within your first two hours. Push that early as a draft PR and tell me.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T15 · Frontend shell

Folder `../ditto-T15-web` · branch `feat/T15-web` · agent B-web · consumer sign-off: B-api (T14)

```text
You are the B-web agent, a Builder, for task T15 (Frontend shell), working in this git worktree on branch feat/T15-web.
1. Read CLAUDE.md (especially the coordination board section), the T15 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T15.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T15-web`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Develop against P2D_RUNNER=fake (the replay runner); never call real models. Until T14's replay runner merges, drive the UI straight from fixtures/events/plant_monitor.jsonl.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T16 · Pricing and memory

Folder `../ditto-T16-bom` · branch `feat/T16-bom` · agent B-bom · consumer sign-off: B-web (T15) and B-agent (T13)

```text
You are the B-bom agent, a Builder, for task T16 (Pricing and memory), working in this git worktree on branch feat/T16-bom.
1. Read CLAUDE.md (especially the coordination board section), the T16 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T16.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T16-bom`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Mock every Nexar HTTP call in tests; only scripts/prefetch_prices.py touches the real API. Check Nexar's query and field names in its schema explorer before coding.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T17 · Input preprocessing

Folder `../ditto-T17-input` · branch `feat/T17-input` · agent B-bom · consumer sign-off: B-agent (T13)

```text
You are the B-bom agent, a Builder, for task T17 (Input preprocessing), working in this git worktree on branch feat/T17-input.
1. Read CLAUDE.md (especially the coordination board section), the T17 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T17.md, commit.
5. Build in small commits. Run `make lint test` (and `make test-slow`, which your card lists) as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T17-input`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Small task: keep it under two hours. Mock transcription in unit tests.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T18 · Parts library expansion

Folder `../ditto-T18-parts` · branch `feat/T18-parts` · agent B-parts · consumer sign-off: B-fw (T12/T23)

```text
You are the B-parts agent, a Builder, for task T18 (Parts library expansion), working in this git worktree on branch feat/T18-parts.
1. Read CLAUDE.md (especially the coordination board section), the T18 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T18.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T18-parts`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Every pin, voltage and I2C address needs a `source:` URL. Never guess a pinout or a `wokwi_type`; leave a field empty and say so in your status file rather than invent it. A human will spot-check three parts against datasheets.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T19 · QA test suite (test-first)

Folder `../ditto-T19-qa` · branch `feat/T19-qa` · role QA · consumer sign-off: Integrator

```text
You are QA (Q) for task T19, working in this git worktree on branch feat/T19-qa.
1. Read CLAUDE.md (especially the coordination board section), the T19 card in section 5 and section 7
   (testing strategy) of handoff/BUILD_PLAN.md, everything in backend/contracts/ and fixtures/, and
   docs/PROJECT_PLAN.md.
2. Run `python3 scripts/board.py next`. It should say START (or QA_UPDATE for T00/T01: acknowledge those
   with `python3 scripts/board.py ack T00` and `ack T01` once you've read them).
3. Write tests from the contracts and the docs only, never from another agent's implementation (don't read
   other feat/ branches). Propose a plan: the integration tests, the two end-to-end tests
   (test_plant_monitor.py, test_edits.py), the shared invariant helpers, and the evals skeleton. Wait for my approval.
4. After approval: `python3 scripts/board.py start`, write your plan into handoff/status/T19.md, commit.
5. Mark every test that can't pass yet as xfail with the blocking task ID in the reason, e.g.
   reason="needs T11 (layout)". The suite must run green (with xfails) on main.
6. Submit early: when the helpers and first tests are ready, rebase, push, open a PR,
   `python3 scripts/board.py submit`. After it merges, keep adding tests in new commits and resubmit.
7. From then on, follow `python3 scripts/board.py next`. Each QA_UPDATE means a task just merged:
   rebase, un-xfail what now passes, report what still fails, then `board.py ack <TASK>`.
```

### T20 · Integration (Gate G1)

Main folder · branch `main` · role Integrator. Type `/clear` in the Integrator tab first.

```text
You are the Integrator (I). Read CLAUDE.md, the T20 card and section 8 of handoff/BUILD_PLAN.md and
handoff/HARDWARE.md. Run `python3 scripts/board.py next`; it should show WORK for T20 (T10–T16 merged).
Goal: Gate G1, the plant-monitor prompt running end to end from the web app with real tools and a real model.
1. Propose a plan: switching to P2D_RUNNER=real with AgentRunner(real_toolbox()), what you'll run to find
   glue problems, and how you'll coordinate fixes. Wait for my approval.
2. Fix glue only in files you own (backend/tools/toolbox.py). A fix in another task's file needs that
   owner: file it as a contract request or tell me the exact change and I'll pass it on.
3. Keep handling MERGE and DECIDE_CONTRACT actions from `board.py next` while you work; they unblock others.
4. Run tests/e2e/test_plant_monitor.py with the real runner. When it passes, push, run
   `python3 scripts/board.py done T20` and `python3 scripts/board.py announce "G1 passed: real runner works end to end"`,
   and show me the test output.
```

### T21 · Cross-domain checks

Folder `../ditto-T21-cross-checks` · branch `feat/T21-cross-checks` · agent B-validate · consumer sign-off: B-web (T24)

```text
You are the B-validate agent, a Builder, for task T21 (Cross-domain checks), working in this git worktree on branch feat/T21-cross-checks.
1. Read CLAUDE.md (especially the coordination board section), the T21 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T21.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T21-cross-checks`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Reuse QA's invariant helpers in tests/ if they're merged; don't duplicate them. Test each check by corrupting a copy of a real run folder.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T22 · Edit and rerun flow

Folder `../ditto-T22-edits` · branch `feat/T22-edits` · agent B-api · consumer sign-off: B-web (T24) and QA (T30)

```text
You are the B-api agent, a Builder, for task T22 (Edit and rerun flow), working in this git worktree on branch feat/T22-edits.
1. Read CLAUDE.md (especially the coordination board section), the T22 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T22.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T22-edits`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Rerun stale stages through `run_stages`; fixtures/events/plant_monitor_edit.jsonl shows the expected stream. Deterministic stages rerun without calling the model; prove it in a test that counts model calls for a wall-thickness edit.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T23 · Library snippet compile

Folder `../ditto-T23-snippets` · branch `feat/T23-snippets` · agent B-fw · consumer sign-off: B-parts (T18)

```text
You are the B-fw agent, a Builder, for task T23 (Library snippet compile), working in this git worktree on branch feat/T23-snippets.
1. Read CLAUDE.md (especially the coordination board section), the T23 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T23.md, commit.
5. Build in small commits. Run `make lint test` (and `make test-slow`, which your card lists) as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T23-snippets`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: You may fix snippets in backend/parts/snippets/ (ownership passed to you after T18 merged). Don't change pinouts in the YAML files; report suspected pinout errors instead.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T24 · Frontend live hookup

Folder `../ditto-T24-web-live` · branch `feat/T24-web-live` · agent B-web · consumer sign-off: QA (T30)

```text
You are the B-web agent, a Builder, for task T24 (Frontend live hookup), working in this git worktree on branch feat/T24-web-live.
1. Read CLAUDE.md (especially the coordination board section), the T24 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T24.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T24-web-live`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Show the agent's live plan (`plan` events), questions (`waiting` status), stale badges, the assembly toggle once T25 merges, and the simulation panel.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T25 · Assembly preview

Folder `../ditto-T25-assembly` · branch `feat/T25-assembly` · agent B-cad · consumer sign-off: B-web (T24)

```text
You are the B-cad agent, a Builder, for task T25 (Assembly preview), working in this git worktree on branch feat/T25-assembly.
1. Read CLAUDE.md (especially the coordination board section), the T25 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T25.md, commit.
5. Build in small commits. Run `make lint test` (and `make test-slow`, which your card lists) as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T25-assembly`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Check positions numerically against the layout, not by eye. Required in hardware modes E and V.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T26 · Simulation (Wokwi)

Folder `../ditto-T26-simulation` · branch `feat/T26-simulation` · agent B-parts · consumer sign-off: B-fw (T31)

```text
You are the B-parts agent, a Builder, for task T26 (Simulation (Wokwi)), working in this git worktree on branch feat/T26-simulation.
1. Read CLAUDE.md (especially the coordination board section), the T26 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T26.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T26-simulation`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Check wokwi-cli's current flags in Wokwi's docs before coding. With no WOKWI_CLI_TOKEN, return a `skipped` result, not a failure. Required in hardware mode V.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T30 · Evals and demo cache

Folder `../ditto-T30-evals` · branch `feat/T30-evals` · role QA · consumer sign-off: Integrator

```text
You are QA (Q) for task T30, working in this git worktree on branch feat/T30-evals.
Read CLAUDE.md, the T30 card and section 1 (G3 bar) of handoff/BUILD_PLAN.md, and handoff/HARDWARE.md.
Example prompt 3, from the makerspace interview, is: <PASTE THE PROMPT FROM H3>
1. Run `python3 scripts/board.py next`; it should say START (handle any QA_UPDATE first).
2. Propose a plan: evals/prompts.yaml (plant monitor, the assistive-device prompt, prompt 3), 5 runs each,
   what counts as a pass (every check passed), the report format, and how you'll record cached runs for
   P2D_RUNNER=replay:<dir>. Wait for my approval.
3. After approval: `python3 scripts/board.py start`. Run the evals (they call the real model: tell me
   the expected number of runs before starting).
4. Report the pass rate per prompt and, for each failure, the stage and error. Record the best run of each
   prompt to evals/cache/. Then rebase, push, open a PR, `python3 scripts/board.py submit`, and keep
   following `board.py next` until it says DONE.
```

### T31 · Showcase device

Folder `../ditto-T31-device` · branch `feat/T31-device` · agent B-fw · consumer sign-off: Integrator

```text
You are the B-fw agent, a Builder, for task T31 (showcase device), working in this git worktree on
branch feat/T31-device.
The team chose this device: <PASTE THE TWO OR THREE SENTENCES FROM H2>
The hardware mode in handoff/HARDWARE.md is: <P, E or V>
1. Read CLAUDE.md, the T31 card and section 0 of handoff/BUILD_PLAN.md, backend/contracts/, and the
   library YAML for every part the device uses. Confirm every part has a wokwi_type; tell me if not.
2. Run `python3 scripts/board.py next`; it should say START.
3. The device must be designed by our own tool: run the prompt through the app (P2D_RUNNER=real) and use
   that run's spec, firmware and enclosure as the starting point. Tell me the run ID.
4. Propose a plan: firmware changes in device/, the relay endpoint in backend/app/routers/device.py
   (holds the API key; the device never does), the tests, and the acceptance check for our mode. Wait for
   my approval, then `python3 scripts/board.py start`.
5. Build and test. For mode P or E, list the exact wiring steps a human should follow on the bench,
   generated from the spec's connections. Then rebase, push, open a PR, `python3 scripts/board.py submit`,
   and keep following `board.py next` until it says DONE.
```

### T32 · Inventory and explain UI

Superseded by T36 (no session).

### T36 · UI merge: Ditto V2 design

Folder `../ditto-T36-ui-merge` · branch `feat/T36-ui-merge` · agent B-web · consumer sign-off: QA (T30)

```text
You are the B-web agent, a Builder, for task T36 (UI merge: Ditto V2 design), working in this git worktree on branch feat/T36-ui-merge.
1. Read CLAUDE.md (especially the coordination board section), the T36 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T36.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T36-ui-merge`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: The design is the Figma file "Ditto V2" (frames on the card); read it through the Figma MCP
(budget: Starter/View seats get 20 calls a month). Use only the existing endpoints; anything without
backend data is a static placeholder that names the task that will connect it.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T37 · User profile: skill level and name

Folder `../ditto-T37-profile` · branch `feat/T37-profile` · agent B-agent · consumer sign-off: B-web (T36/T40)

```text
You are the B-agent agent, a Builder, for task T37 (User profile: skill level and name), working in this git worktree on branch feat/T37-profile.
1. Read CLAUDE.md (especially the coordination board section), the T37 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T37.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T37-profile`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: File the UserContext change as a contract request first and build the prompt side against it.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T38 · Several store offers per part

Folder `../ditto-T38-offers` · branch `feat/T38-offers` · agent B-bom · consumer sign-off: B-web (T36/T40)

```text
You are the B-bom agent, a Builder, for task T38 (Several store offers per part), working in this git worktree on branch feat/T38-offers.
1. Read CLAUDE.md (especially the coordination board section), the T38 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T38.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T38-offers`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: File the BomLine.offers change as a contract request first; mock every Nexar call in tests.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T39 · Run list and cancel endpoints

Folder `../ditto-T39-run-list` · branch `feat/T39-run-list` · agent B-api · consumer sign-off: B-web (T36/T40)

```text
You are the B-api agent, a Builder, for task T39 (Run list and cancel endpoints), working in this git worktree on branch feat/T39-run-list.
1. Read CLAUDE.md (especially the coordination board section), the T39 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T39.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T39-run-list`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Read runs only from the run directories (spec.json, events.jsonl); no new storage.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T40 · Build guide screens

Folder `../ditto-T40-build-guide` · branch `feat/T40-build-guide` · agent B-web · consumer sign-off: QA (T30)

```text
You are the B-web agent, a Builder, for task T40 (Build guide screens), working in this git worktree on branch feat/T40-build-guide.
1. Read CLAUDE.md (especially the coordination board section), the T40 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T40.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T40-build-guide`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: The design is the Figma file "Ditto V2", frames 25:735 and 28:900; build on T36's components and tokens.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T33 · Docs and Devpost

Folder `../ditto-T33-docs` · branch `feat/T33-docs` · agent B-agent · consumer sign-off: humans

```text
You are the B-agent agent, a Builder, for task T33 (Docs and Devpost), working in this git worktree on branch feat/T33-docs.
1. Read CLAUDE.md (especially the coordination board section), the T33 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T33.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T33-docs`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Write for judges and for a teammate on a clean machine. Include the track notes from the card. Verify every command in the README by running it.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T34 · Stretch: tscircuit board preview

Folder `../ditto-T34-tscircuit` · branch `feat/T34-tscircuit` · agent B-cad · consumer sign-off: B-web

```text
You are the B-cad agent, a Builder, for task T34 (Stretch: tscircuit board preview), working in this git worktree on branch feat/T34-tscircuit.
1. Read CLAUDE.md (especially the coordination board section), the T34 card in section 5 of
   handoff/BUILD_PLAN.md, everything in backend/contracts/, handoff/HARDWARE.md, and the parts of
   docs/PROJECT_PLAN.md your card mentions.
2. Run `python3 scripts/board.py next`. It should say START. If it says anything else, tell me what it
   says and stop.
3. Propose a plan: the files you'll create or change (only paths your card owns), one test per acceptance
   criterion, and the order you'll build in. Wait for my approval.
4. After approval: run `python3 scripts/board.py start`, write your plan into handoff/status/T34.md, commit.
5. Build in small commits. Run `make lint test` as you go.
6. When every acceptance criterion passes: `git rebase origin/main`, rerun the tests, push
   (`git push -u origin feat/T34-tscircuit`, with --force-with-lease after a rebase), open a PR with
   `gh pr create --fill --base main`, then `python3 scripts/board.py submit`.
7. From then on, follow `python3 scripts/board.py next`: fix review notes, sign off other agents' work
   when asked, rebase when told. When it says DONE, tell me and stop.
Notes for this task: Optional and time-boxed: stop and report at hour 32 whatever state it's in.
If a contract looks wrong or you need a file you don't own, file a contract request (CLAUDE.md explains
how) and keep going with the current contract. Don't work around it.
```

### T35 · Release check

Review folder `../ditto-review` · role Reviewer. Type `/clear` in the Reviewer tab first.

```text
You are the Reviewer (R), now doing task T35, the release check. Read CLAUDE.md, the T35 card and
section 0 of handoff/BUILD_PLAN.md, and handoff/HARDWARE.md. Run `python3 scripts/board.py next`: finish
any REVIEW actions first; then it shows WORK for T35.
1. `git fetch && git checkout --detach origin/main`, then run `make setup lint test test-slow` and
   one `make test-live` run of tests/e2e/test_plant_monitor.py.
2. Scan the whole git history for secrets (gitleaks if installed, otherwise grep for key prefixes).
3. Follow README.md step by step as a new teammate would; list every step that fails or is unclear.
4. Write a demo rehearsal checklist for our hardware mode, plus the cached-run fallback
   (P2D_RUNNER=replay:<dir>).
Report: PASS or the list of blockers, most serious first. Don't fix code yourself. If everything passes,
run `python3 scripts/board.py done T35` and tell me, and I'll ask the Integrator to tag v1.0-demo.
```
