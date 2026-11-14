#!/usr/bin/env python3
"""Coordination board for the Prompt-to-Device hackathon build.

One shared, always-current answer to "what should I do next?" for every agent and human.

* The static plan (who depends on whom, who consumes whose output) is `handoff/tasks.json` on main.
* The live state (started, submitted, reviewed, signed off, merged, contract requests) lives on a
  separate git branch, `coord`, as `state.json` + `log.jsonl`. It is written only by this script,
  with an atomic commit-and-push that retries on conflict, so many agents on many machines can
  update it at once. Nothing on `coord` is ever edited by hand or merged into main.

Agents mostly run `python3 scripts/board.py next`. It prints one ACTION with exact instructions.
Run `python3 scripts/board.py --help` for every command. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import signal
import subprocess
import sys
import time

DONE_STATES = {"merged", "done", "skipped"}
ROLE_FOR_KIND = {"builder": "builder", "qa": "qa", "reviewer": "reviewer", "main": "integrator"}


class BoardError(Exception):
    pass


# ----------------------------------------------------------------------------- git helpers

def git(*args: str, check: bool = True, input_text: str | None = None, env: dict | None = None) -> str:
    # Bytes in, bytes out: text mode on Windows turns "\n" into "\r\n" on stdin, which corrupts the
    # tree that `git mktree` builds (file names end up as "state.json\r").
    proc = subprocess.run(["git", *args], capture_output=True,
                          input=input_text.encode("utf-8") if input_text is not None else None,
                          env={**os.environ, **(env or {})})
    out = proc.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise BoardError(f"git {' '.join(args)} failed: {err}")
    return out.strip()


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], capture_output=True).returncode == 0


def toplevel() -> str:
    return git("rev-parse", "--show-toplevel")


def use_remote() -> bool:
    if os.environ.get("P2D_BOARD_LOCAL") == "1":
        return False
    return "origin" in git("remote", check=False).split()


def ref(name: str) -> str:
    return f"origin/{name}" if use_remote() else name


def rev(name: str) -> str | None:
    out = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{name}^{{commit}}"],
                         capture_output=True, text=True)
    return out.stdout.strip() or None


def is_ancestor(a: str | None, b: str | None) -> bool:
    return bool(a and b) and git_ok("merge-base", "--is-ancestor", a, b)


_fetched = False


def fetch(force: bool = False) -> None:
    global _fetched
    if not use_remote() or (_fetched and not force):
        return
    proc = subprocess.run(["git", "fetch", "-q", "--prune", "origin"], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"(warning: git fetch failed, showing last known state: {proc.stderr.strip()})", file=sys.stderr)
    _fetched = True


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def age(ts: str | None) -> str:
    if not ts:
        return "-"
    try:
        mins = int((dt.datetime.now().astimezone() - dt.datetime.fromisoformat(ts)).total_seconds() // 60)
    except ValueError:
        return ts
    return f"{mins}m ago" if mins < 120 else f"{mins // 60}h ago"


# ----------------------------------------------------------------------------- plan + state

def load_plan() -> dict:
    fetch()
    main = rev(ref("main"))
    text = None
    if main:
        text = subprocess.run(["git", "show", f"{main}:handoff/tasks.json"],
                              capture_output=True, text=True, encoding="utf-8").stdout or None
    if not text:
        with open(os.path.join(toplevel(), "handoff", "tasks.json"), encoding="utf-8") as f:
            text = f.read()
    plan = json.loads(text)
    plan["by_id"] = {t["id"]: t for t in plan["tasks"]}
    return plan


def hardware_mode() -> str:
    main = rev(ref("main"))
    text = ""
    if main:
        text = subprocess.run(["git", "show", f"{main}:handoff/HARDWARE.md"], capture_output=True, text=True, encoding="utf-8").stdout
    for line in text.splitlines():
        if line.strip().startswith("MODE="):
            value = line.split("=", 1)[1].split("#")[0].strip().upper()
            if value in {"P", "E", "V"}:
                return value
    return "V"  # BUILD_PLAN section 0: build for the strictest mode until decided


def read_state() -> tuple[dict | None, str | None]:
    fetch()
    sha = rev(ref("coord"))
    if not sha:
        return None, None
    return json.loads(git("show", f"{sha}:state.json")), sha


def commit_state(state: dict, parent: str | None, event: dict) -> str:
    log = git("show", f"{parent}:log.jsonl", check=False) if parent else ""
    log = (log + "\n" if log else "") + json.dumps(event, sort_keys=True)
    state_blob = git("hash-object", "-w", "--stdin", input_text=json.dumps(state, indent=1, sort_keys=True) + "\n")
    log_blob = git("hash-object", "-w", "--stdin", input_text=log + "\n")
    tree = git("mktree", input_text=f"100644 blob {log_blob}\tlog.jsonl\n100644 blob {state_blob}\tstate.json\n")
    ident = {}
    if not git("config", "user.name", check=False):
        ident.update(GIT_AUTHOR_NAME="p2d-board", GIT_COMMITTER_NAME="p2d-board")
    if not git("config", "user.email", check=False):
        ident.update(GIT_AUTHOR_EMAIL="board@p2d.local", GIT_COMMITTER_EMAIL="board@p2d.local")
    args = ["commit-tree", tree, "-m", f"board: {event.get('summary', '')}"]
    if parent:
        args[2:2] = ["-p", parent]
    return git(*args, env=ident)


def publish(commit: str, parent: str | None) -> bool:
    if use_remote():
        return subprocess.run(["git", "push", "-q", "origin", f"{commit}:refs/heads/coord"],
                              capture_output=True).returncode == 0
    old = parent or "0" * 40
    return git_ok("update-ref", "refs/heads/coord", commit, old)


def update(mutate, summary: str, actor: str):
    """Read-modify-write the board atomically; retries if someone else wrote first."""
    for attempt in range(10):
        fetch(force=True)
        state, parent = read_state()
        if state is None:
            raise BoardError("The board isn't initialised yet. The Integrator runs: python3 scripts/board.py init")
        result = mutate(state)
        state["updated_at"] = now()
        event = {"at": state["updated_at"], "by": actor, "summary": summary}
        commit = commit_state(state, parent, event)
        if publish(commit, parent):
            return result
        time.sleep(1 + random.random() * 2 * (attempt + 1))
    raise BoardError("Couldn't write to the board after 10 tries (network or constant conflicts). Try again.")


def task_state(state: dict, tid: str) -> dict:
    return state["tasks"].setdefault(tid, {"state": "not_started"})


# ----------------------------------------------------------------------------- identity

def whoami(args) -> dict:
    """Agent identity from .env.worktree; the main checkout is the Integrator."""
    if getattr(args, "as_", None):
        who = args.as_
        if who == "human":
            return {"agent": "human", "role": "human", "task": None}
        plan = load_plan()
        seq = plan["agents"].get(who)
        if seq is None:
            raise BoardError(f"Unknown agent {who}. Agents: {', '.join(plan['agents'])}, human")
        role = "integrator" if who == "I" else "reviewer" if who == "R" else "qa" if who == "Q" else "builder"
        return {"agent": who, "role": role, "task": os.environ.get("P2D_TASK")}
    env = {}
    path = os.path.join(toplevel(), ".env.worktree")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    if env.get("P2D_AGENT"):
        return {"agent": env["P2D_AGENT"], "role": env.get("P2D_ROLE", "builder"), "task": env.get("P2D_TASK")}
    if git("rev-parse", "--git-dir") == git("rev-parse", "--git-common-dir"):
        return {"agent": "I", "role": "integrator", "task": None}
    raise BoardError("Can't tell who you are: no .env.worktree here. Pass --as <agent> (e.g. --as B-web or --as human).")


# ----------------------------------------------------------------------------- derived facts

class Board:
    def __init__(self, plan: dict, state: dict):
        self.plan, self.state = plan, state
        self.mode = hardware_mode()
        self.main = rev(ref("main"))

    def t(self, tid: str) -> dict:
        return self.plan["by_id"][tid]

    def st(self, tid: str) -> dict:
        return self.state["tasks"].get(tid, {"state": "not_started"})

    def skipped_by_mode(self, tid: str) -> bool:
        modes = self.t(tid).get("modes")
        return bool(modes) and self.mode not in modes

    def required(self, tid: str) -> bool:
        t = self.t(tid)
        if t.get("optional") or self.skipped_by_mode(tid):
            return False
        req = t.get("required_in")
        return not req or self.mode in req

    def done(self, tid: str) -> bool:
        return self.st(tid)["state"] in DONE_STATES or self.skipped_by_mode(tid)

    def deps(self, tid: str) -> list[str]:
        t = self.t(tid)
        return list(t["deps"]) + list(t.get("deps_in_mode", {}).get(self.mode, []))

    def unmet(self, tid: str) -> list[str]:
        return [d for d in self.deps(tid) if not self.done(d)]

    def head(self, tid: str) -> str | None:
        branch = self.t(tid).get("branch")
        return rev(ref(branch)) if branch else None

    def approval_valid(self, tid: str) -> bool:
        review = self.st(tid).get("review") or {}
        return review.get("verdict") == "approve" and review.get("sha") == self.head(tid)

    def missing_signoffs(self, tid: str) -> list[str]:
        head = self.head(tid)
        signoffs = self.st(tid).get("signoffs", {})
        return [c for c in self.t(tid)["consumers"]
                if not (signoffs.get(c, {}).get("verdict") == "ok" and signoffs.get(c, {}).get("sha") == head)]

    def mergeable(self, tid: str) -> bool:
        return self.st(tid)["state"] == "in_review" and self.approval_valid(tid) and not self.missing_signoffs(tid)

    def needs_review(self, tid: str) -> bool:
        s = self.st(tid)
        if s["state"] != "in_review":
            return False
        review = s.get("review") or {}
        return review.get("sha") != self.head(tid)

    def ready_to_start(self) -> list[str]:
        """Tasks a human should open a session for now."""
        out = []
        for agent, seq in self.plan["agents"].items():
            for tid in seq:
                if self.done(tid):
                    continue
                if self.st(tid)["state"] == "not_started" and not self.unmet(tid):
                    out.append(tid)
                break  # an agent works one task at a time, in order
        for t in self.plan["tasks"]:
            if t["kind"] == "human" and not self.done(t["id"]) and not self.unmet(t["id"]):
                out.append(t["id"])
        return out

    def next_by(self, tid: str) -> str:
        t, s = self.t(tid), self.st(tid)["state"]
        if self.skipped_by_mode(tid):
            return f"skipped (mode {self.mode})"
        if s in DONE_STATES:
            return "-"
        if self.unmet(tid):
            return "waits for " + ",".join(self.unmet(tid))
        if s == "not_started":
            return "human: start it" if t["kind"] != "human" else f"Person {t['person']}"
        if s == "changes_requested":
            return f"{t.get('agent')}: fix review"
        if s == "blocked":
            return f"blocked on {self.st(tid).get('blocked_on') or '?'}"
        if s == "in_review":
            if self.head(tid) != self.st(tid).get("submitted_sha") and not self.approval_valid(tid):
                return f"{t.get('agent')}: resubmit"
            if not self.approval_valid(tid):
                return "R: review"
            missing = self.missing_signoffs(tid)
            return "sign-off: " + ",".join(missing) if missing else "I: merge"
        return t.get("agent") or f"Person {t['person']}"


# ----------------------------------------------------------------------------- next-action engine

def action(kind: str, text: str) -> tuple[str, str]:
    return kind, text.strip()


def actions_for(board: Board, me: dict) -> list[tuple[str, str]]:
    acts: list[tuple[str, str]] = []
    agent, role, my = me["agent"], me["role"], me["task"]
    st = board.state

    # Contract requests (Integrator)
    if role == "integrator":
        for req in st.get("requests", []):
            if req["status"] == "open":
                acts.append(action("DECIDE_CONTRACT", f"""
Contract request #{req['id']} from {req['task']}: {req['summary']}
Read it: git show {ref(req['branch'])}:{req['file']}
Decide per section 8 of handoff/BUILD_PLAN.md. Then record it:
  python3 scripts/board.py decide {req['id']} accept|reject --notes "<decision and who must change what>"
If accepted: land the change on main as its own commit, bump CONTRACT_VERSION, then
  python3 scripts/board.py announce "contract change: <summary>" --rebase"""))
        for tid in sorted((t for t in board.plan["by_id"] if board.mergeable(t)),
                          key=lambda x: board.st(x).get("submitted_at", "")):
            t = board.t(tid)
            acts.append(action("MERGE", f"""
{tid} ({t['title']}) is approved and signed off at {board.head(tid)[:8]}.
1. git fetch && git checkout main && git pull
2. git merge --no-ff {ref(t['branch'])}  (a merge commit: never squash or rebase-merge)
3. make lint test{' && make test-slow' if t.get('slow') else ''}  -- if anything fails, don't push; tell the builder.
4. git push origin main
5. python3 scripts/board.py merged {tid}
6. Append a line to handoff/MERGES.md (hour, sha, task, one line), commit and push."""))
        for tid in ("T00", "T01", "T20"):
            if not board.done(tid) and not board.unmet(tid):
                acts.append(action("WORK", f"""
Your task {tid} ({board.t(tid)['title']}) is ready. Follow its card in section 5 of handoff/BUILD_PLAN.md.
When it's finished and pushed to main: python3 scripts/board.py done {tid}"""))
                break

    # Reviews (Reviewer)
    if role == "reviewer":
        queue = sorted((t for t in board.plan["by_id"] if board.needs_review(t)),
                       key=lambda x: board.st(x).get("submitted_at", ""))
        for tid in queue:
            t = board.t(tid)
            acts.append(action("REVIEW", f"""
Review {tid} ({t['title']}), branch {t['branch']} at {board.head(tid)[:8]}.
  git fetch && git checkout --detach {ref(t['branch'])}
  uv sync && make lint test{' && make test-slow' if t.get('slow') else ''}
  git diff --stat {ref('main')}...{ref(t['branch'])}   # scope: only the paths its card owns
Use the checklist in section 6 of handoff/BUILD_PLAN.md against the {tid} card in section 5.
Record the verdict (the builder and Integrator see it automatically):
  python3 scripts/board.py review {tid} approve --notes "<one line>"
  python3 scripts/board.py review {tid} changes --notes-file /tmp/{tid}-review.md   # numbered list"""))
        if not board.done("T35") and not board.unmet("T35"):
            acts.append(action("WORK", "Task T35 (release check) is ready: follow its card, then run "
                                       "python3 scripts/board.py done T35 when it passes."))

    # My own task (builders and QA)
    mine: list[tuple[str, str]] = []
    if role in ("builder", "qa") and my:
        t, s = board.t(my), board.st(my)
        state = s["state"]
        if state in DONE_STATES:
            seq = board.plan["agents"].get(agent, [])
            later = [x for x in seq[seq.index(my) + 1:] if not board.done(x)] if my in seq else []
            if later:
                nxt = later[0]
                why = ("ready now" if not board.unmet(nxt)
                       else "waits for " + ", ".join(f"{d} ({board.st(d)['state']})" for d in board.unmet(nxt)))
                mine.append(action("DONE", f"""
{my} is {state}. You're finished in this worktree. Tell your human:
"Agent {agent}: {my} merged. Next task {nxt} ({board.t(nxt)['title']}): {why}.
 Start it with: scripts/setup_worktrees.sh add {nxt} {board.t(nxt).get('slug', '')} and a new session." """))
            else:
                mine.append(action("DONE", f"{my} is {state} and agent {agent} has no further tasks. Tell your human."))
        elif board.unmet(my):
            mine.append(action("WAIT", "Your task's dependencies aren't merged yet: " +
                               ", ".join(f"{d} ({board.st(d)['state']}, next: {board.next_by(d)})" for d in board.unmet(my))))
        elif state == "not_started":
            mine.append(action("START", f"""
Your task {my} ({t['title']}) is ready to start. Propose your plan as the kickoff prompt says; once it's
approved, record the start:  python3 scripts/board.py start"""))
        elif state == "changes_requested":
            review = s.get("review", {})
            mine.append(action("FIX_REVIEW", f"""
The Reviewer requested changes on {my} (reviewed {str(review.get('sha'))[:8]}):
{review.get('notes', '(no notes)')}
Fix each item or explain why you disagree, rerun the tests, rebase on main, push, then:
  python3 scripts/board.py submit"""))
        elif state == "blocked":
            blockers = [b for b in (s.get("blocked_on") or "").split(",") if b]
            if blockers and all(b in board.plan["by_id"] and board.done(b) for b in blockers):
                mine.append(action("UNBLOCKED", f"What you were blocked on ({', '.join(blockers)}) is done. "
                                                "Rebase on main, then: python3 scripts/board.py unblock"))
            else:
                mine.append(action("WAIT", f"You're blocked on {s.get('blocked_on')}: {s.get('notes', '')}"))
        elif state == "in_review":
            if board.head(my) != s.get("submitted_sha") and not board.approval_valid(my):
                mine.append(action("RESUBMIT", "You pushed commits after submitting. If they're ready, "
                                               "run: python3 scripts/board.py submit"))
            elif not board.approval_valid(my):
                queue = sorted((x for x in board.plan["by_id"] if board.needs_review(x)),
                               key=lambda x: board.st(x).get("submitted_at", ""))
                pos = queue.index(my) + 1 if my in queue else "?"
                mine.append(action("WAIT", f"{my} is waiting for review (position {pos} in the Reviewer's queue). "
                                           "Don't push new commits unless you mean to resubmit."))
            elif board.missing_signoffs(my):
                mine.append(action("WAIT", f"{my} is approved; waiting for consumer sign-off from: "
                                           + ", ".join(board.missing_signoffs(my))))
            else:
                mine.append(action("WAIT", f"{my} is approved and signed off; waiting for the Integrator to merge it."))
        else:  # in_progress
            mine.append(action("WORK", f"""
Keep working on {my} ({t['title']}) per its card. When every acceptance criterion passes:
  git rebase {ref('main')} && make lint test{' && make test-slow' if t.get('slow') else ''}
  git push -u origin {t.get('branch')}
  python3 scripts/board.py submit
If you're stuck on another task: python3 scripts/board.py block --on <TASK> --notes "<why>" """))

    # Sign-off requests addressed to my agent (only once the Reviewer has approved)
    signoffs = []
    if role in ("builder", "qa", "integrator", "human"):
        for tid in board.plan["by_id"]:
            if (board.st(tid)["state"] == "in_review" and board.approval_valid(tid)
                    and agent in board.missing_signoffs(tid)):
                t = board.t(tid)
                signoffs.append(action("SIGNOFF", f"""
{tid} ({t['title']}) is approved and needs your consumer sign-off as {agent}.
  git worktree add --detach ../p2d-check-{tid} {ref(t['branch'])}
  git diff {ref('main')}...{ref(t['branch'])}     # read what changed in the parts you use
Check that what your work needs from it behaves as your card expects (run your relevant tests or a
short script against ../p2d-check-{tid}). Change nothing there. Then:
  python3 scripts/board.py signoff {tid} ok --notes "<one line>"    # or: fail --notes "<what breaks>"
  git worktree remove ../p2d-check-{tid}"""))

    # Rebase needed? (merges I consume, my soft deps, announced contract changes)
    rebase = []
    if role in ("builder", "qa") and my and board.st(my)["state"] in ("in_progress", "changes_requested", "blocked"):
        head = git("rev-parse", "HEAD")
        watch = set(board.t(my).get("soft", []))
        watch |= {tid for tid, t in board.plan["by_id"].items() if agent in t.get("consumers", [])}
        missing = [tid for tid in sorted(watch)
                   if board.st(tid)["state"] == "merged" and not is_ancestor(board.st(tid).get("merged_sha"), head)]
        for ann in st.get("announcements", []):
            if ann.get("rebase") and not is_ancestor(ann.get("main_sha"), head):
                missing.append(f"announcement: {ann['text']}")
        if missing:
            rebase.append(action("REBASE", f"""
main has changes you depend on that your branch doesn't include yet: {', '.join(missing)}.
At your next stopping point: commit, then
  git fetch && git rebase {ref('main')} && make lint test
Fix anything the rebase broke. If you were faking any of these with a stub, switch to the real code if your card says to."""))

    # QA: react to every merge once
    qa = []
    if role == "qa" and my and not board.done(my):
        acked = set(st.get("qa_ack", []))
        for tid, t in board.plan["by_id"].items():
            if t["kind"] in ("builder", "main") and board.st(tid)["state"] in ("merged", "done") and tid not in acked:
                qa.append(action("QA_UPDATE", f"""
{tid} ({t['title']}) is now on main. Rebase on main, run the integration and e2e tests whose xfail
reason names {tid}, remove xfail from the ones that pass, report the ones that still fail (with the
error) in your status file, then:  python3 scripts/board.py ack {tid}"""))

    # Priority: unblock others first, then my own work
    fix = [a for a in mine if a[0] == "FIX_REVIEW"]
    rest = [a for a in mine if a[0] != "FIX_REVIEW"]
    acts = acts + fix + signoffs + rebase + qa + rest

    if role == "human":
        for tid in board.ready_to_start():
            t = board.t(tid)
            if t["kind"] == "human":
                acts.append(action("HUMAN_TASK", f"Person {t['person']}: {tid} {t['title']}. "
                                                 f"When done: python3 scripts/board.py done {tid} --as human"))
            elif t.get("slug"):
                acts.append(action("START_SESSION", f"Person {t['person']}: start {tid} ({t['title']}) for agent "
                                                    f"{t['agent']}: scripts/setup_worktrees.sh add {tid} {t['slug']}, then a "
                                                    "new session with its kickoff prompt from handoff/RUNBOOK.md."))
            else:
                where = "the Integrator's tab (main folder)" if t["agent"] == "I" else "the Reviewer's tab"
                acts.append(action("START_SESSION", f"Person {t['person']}: {tid} ({t['title']}) is ready. In {where}, "
                                                    "type /clear and paste its kickoff prompt from handoff/RUNBOOK.md."))

    if not [a for a in acts if a[0] != "WAIT"]:
        waits = [a for a in acts if a[0] == "WAIT"]
        if not waits:
            waits = [action("WAIT", "Nothing for you right now.")]
        starts = [x for x in board.ready_to_start() if board.t(x)["kind"] != "human"]
        if role == "integrator" and starts:
            waits[0] = (waits[0][0], waits[0][1] + "\nTell the humans these tasks can start now: " +
                        ", ".join(f"{x} (Person {board.t(x)['person']})" for x in starts))
        return waits
    return [a for a in acts if a[0] != "WAIT"]


# ----------------------------------------------------------------------------- commands

def cmd_init(args):
    plan = load_plan()
    state, _ = read_state()
    if state is not None and not args.force:
        raise BoardError("The board already exists. Use --force only if you mean to wipe it.")
    fresh = {"version": 1, "created_at": now(), "tasks": {t["id"]: {"state": "not_started"} for t in plan["tasks"]},
             "requests": [], "announcements": [], "qa_ack": []}
    parent = rev(ref("coord")) if args.force else None
    commit = commit_state(fresh, parent, {"at": now(), "by": "I", "summary": "board initialised"})
    if not publish(commit, parent):
        raise BoardError("Couldn't publish the board (someone else created it?). Run status to check.")
    print("Board initialised on branch 'coord'.")


def print_actions(acts, as_json=False):
    if as_json:
        print(json.dumps([{"action": k, "text": v} for k, v in acts], indent=1))
        return
    kind, text = acts[0]
    print(f"ACTION: {kind}\n{text}")
    if len(acts) > 1:
        print("\nAlso pending after this: " + "; ".join(f"{k} {v.splitlines()[0][:60]}" for k, v in acts[1:]))
    print("\n(After acting, run `python3 scripts/board.py next` again.)")


def compute(args):
    me = whoami(args)
    plan = load_plan()
    state, _ = read_state()
    if state is None:
        return me, [("WAIT", "The board isn't initialised yet (the Integrator runs `python3 scripts/board.py init` at Gate G0).")]
    return me, actions_for(Board(plan, state), me)


def cmd_next(args):
    global _fetched
    deadline = time.time() + args.wait
    while True:
        _fetched = False
        me, acts = compute(args)
        if acts[0][0] != "WAIT" or time.time() >= deadline:
            break
        time.sleep(min(args.interval, max(1, deadline - time.time())))
    print_actions(acts, args.json)


def cmd_watch(args):
    """For Claude Code's Monitor tool: print a line whenever the next action changes."""
    global _fetched
    last = None
    while True:
        _fetched = False
        try:
            _, acts = compute(args)
            line = f"{acts[0][0]}: {acts[0][1].splitlines()[0]}"
        except BoardError as e:
            line = f"ERROR: {e}"
        if line != last:
            print(f"[{dt.datetime.now():%H:%M}] {line}", flush=True)
            last = line
        time.sleep(args.interval)


def cmd_whoami(args):
    me = whoami(args)
    print(json.dumps({**me, "mode": hardware_mode(), "remote": use_remote()}, indent=1))


def cmd_status(args):
    plan = load_plan()
    state, _ = read_state()
    if state is None:
        print("Board not initialised yet.")
        return
    board = Board(plan, state)
    print(f"Hardware mode {board.mode} · board updated {age(state.get('updated_at'))} · main {str(board.main)[:8]}\n")
    print(f"{'TASK':5} {'WHO':12} {'STATE':17} {'REVIEW':9} {'SIGN-OFFS':22} NEXT STEP BY")
    for t in plan["tasks"]:
        tid = t["id"]
        s = board.st(tid)
        if not args.all and board.done(tid) and t["kind"] == "human":
            continue
        review = (s.get("review") or {}).get("verdict", "-")
        if review != "-" and (s.get("review") or {}).get("sha") != board.head(tid):
            review += "*"
        cons = t.get("consumers", [])
        sig = ",".join(f"{c}{'✓' if c not in board.missing_signoffs(tid) else '·'}" for c in cons) if cons else "-"
        label = s["state"] + (" (opt)" if not board.required(tid) and not board.skipped_by_mode(tid) else "")
        who = f"{t.get('agent', 'human')}/{t['person']}"
        print(f"{tid:5} {who:12} {label:17} {review:9} {sig:22.22} {board.next_by(tid)}")
    print("\nReview* = review is for an older commit. Sign-offs: ✓ ok at the current commit, · still needed.")
    ready = board.ready_to_start()
    if ready:
        print("\nReady to start now (nobody has run `board.py start` for these yet; the add command skips"
              " a worktree that already exists):")
        for tid in ready:
            t = board.t(tid)
            how = ("" if t["kind"] == "human" else
                   f"  ->  scripts/setup_worktrees.sh add {tid} {t['slug']}" if t.get("slug")
                   else "  ->  Integrator tab (main folder)" if t.get("agent") == "I" else "  ->  Reviewer tab")
            print(f"  {tid} {t['title']} (Person {t['person']}){how}")
    open_reqs = [r for r in state.get("requests", []) if r["status"] == "open"]
    if open_reqs:
        print("\nOpen contract requests: " + "; ".join(f"#{r['id']} {r['task']}: {r['summary']}" for r in open_reqs))
    log = git("show", f"{rev(ref('coord'))}:log.jsonl", check=False).splitlines()[-args.log:]
    if log:
        print("\nRecent board activity:")
        for line in log:
            e = json.loads(line)
            print(f"  {age(e['at']):>8}  {e['by']:10} {e['summary']}")


def own_task(args, me) -> str:
    tid = getattr(args, "task", None) or me["task"]
    if not tid:
        raise BoardError("Which task? Pass it explicitly, e.g. `board.py start T21`.")
    return tid


def cmd_start(args):
    me, plan = whoami(args), load_plan()
    tid = own_task(args, me)
    state, _ = read_state()
    board = Board(plan, state or {"tasks": {}})
    if board.unmet(tid):
        raise BoardError(f"{tid} can't start yet; waiting for: {', '.join(board.unmet(tid))}")

    def m(s):
        task_state(s, tid).update(state="in_progress", started_at=now())
    update(m, f"{tid} started", me["agent"])
    print(f"{tid} is in progress.")


def cmd_submit(args):
    me, plan = whoami(args), load_plan()
    tid = own_task(args, me)
    t = plan["by_id"][tid]
    fetch(force=True)
    dirty = [l for l in git("status", "--porcelain").splitlines() if not l.endswith((".env", ".env.worktree"))]
    if dirty:
        raise BoardError("You have uncommitted changes. Commit them (or stash) before submitting.")
    head = git("rev-parse", "HEAD")
    if not is_ancestor(rev(ref("main")), head):
        raise BoardError(f"Your branch doesn't include the latest main. Run: git rebase {ref('main')}, retest, push, resubmit.")
    if rev(ref(t["branch"])) != head:
        raise BoardError(f"Your latest commit isn't pushed. Run: git push -u origin {t['branch']}  (use --force-with-lease after a rebase)")

    def m(s):
        ts = task_state(s, tid)
        ts.update(state="in_review", submitted_sha=head, submitted_at=now())
    update(m, f"{tid} submitted for review at {head[:8]}", me["agent"])
    print(f"{tid} submitted at {head[:8]}. The Reviewer will pick it up from the board.")


def read_notes(args) -> str:
    if getattr(args, "notes_file", None):
        return open(args.notes_file, encoding="utf-8").read().strip()
    return (getattr(args, "notes", None) or "").strip()


def cmd_review(args):
    me, plan = whoami(args), load_plan()
    if me["role"] != "reviewer" and not args.force:
        raise BoardError("Only the Reviewer records reviews (use --force if a human is overriding).")
    tid = args.task
    fetch(force=True)
    head = rev(ref(plan["by_id"][tid]["branch"]))
    notes = read_notes(args)
    if args.verdict == "changes" and not notes:
        raise BoardError("Requesting changes needs --notes or --notes-file with a numbered list.")

    def m(s):
        ts = task_state(s, tid)
        ts["review"] = {"verdict": args.verdict, "sha": head, "notes": notes, "at": now()}
        if args.verdict == "changes":
            ts["state"] = "changes_requested"
    update(m, f"{tid} review: {args.verdict} at {str(head)[:8]}", me["agent"])
    print(f"Recorded: {tid} {args.verdict} at {str(head)[:8]}.")


def cmd_signoff(args):
    me, plan = whoami(args), load_plan()
    tid = args.task
    t = plan["by_id"][tid]
    if me["agent"] not in t["consumers"]:
        raise BoardError(f"{me['agent']} isn't a consumer of {tid} (consumers: {', '.join(t['consumers']) or 'none'}).")
    fetch(force=True)
    head = rev(ref(t["branch"]))

    def m(s):
        task_state(s, tid).setdefault("signoffs", {})[me["agent"]] = {
            "verdict": args.verdict, "sha": head, "notes": read_notes(args), "at": now()}
        if args.verdict == "fail":
            task_state(s, tid).update(state="changes_requested", review={
                "verdict": "changes", "sha": head, "at": now(),
                "notes": f"Consumer {me['agent']} found a problem: {read_notes(args)}"})
    update(m, f"{tid} sign-off by {me['agent']}: {args.verdict}", me["agent"])
    print(f"Recorded {me['agent']} sign-off for {tid}: {args.verdict}.")


def cmd_merged(args):
    me, plan = whoami(args), load_plan()
    tid = args.task
    fetch(force=True)
    main = rev(ref("main"))
    head = rev(ref(plan["by_id"][tid]["branch"]))
    if not args.force and not is_ancestor(head, main):
        raise BoardError(f"{tid}'s branch head isn't in main yet. Merge (merge commit, no squash) and push first.")

    def m(s):
        task_state(s, tid).update(state="merged", merged_sha=main, merged_at=now())
    update(m, f"{tid} merged into main at {str(main)[:8]}", me["agent"])
    print(f"{tid} marked merged. Agents that depend on it will be told to rebase.")


def cmd_done(args):
    me = whoami(args)
    tid = args.task
    fetch(force=True)
    main = rev(ref("main"))

    def m(s):
        task_state(s, tid).update(state="done", merged_sha=main, merged_at=now())
    update(m, f"{tid} done", me["agent"])
    print(f"{tid} marked done.")


def cmd_block(args):
    me = whoami(args)
    tid = own_task(args, me)

    def m(s):
        task_state(s, tid).update(state="blocked", blocked_on=args.on, notes=args.notes or "")
    update(m, f"{tid} blocked on {args.on}", me["agent"])
    print(f"{tid} marked blocked on {args.on}.")


def cmd_unblock(args):
    me = whoami(args)
    tid = own_task(args, me)

    def m(s):
        task_state(s, tid).update(state="in_progress", blocked_on="", notes="")
    update(m, f"{tid} unblocked", me["agent"])
    print(f"{tid} is in progress again.")


def cmd_request(args):
    me = whoami(args)
    tid = own_task(args, me)
    branch = load_plan()["by_id"][tid].get("branch", "main")

    def m(s):
        rid = len(s.setdefault("requests", [])) + 1
        s["requests"].append({"id": rid, "task": tid, "branch": branch, "file": args.file,
                              "summary": args.summary, "status": "open", "at": now()})
        return rid
    rid = update(m, f"contract request from {tid}: {args.summary}", me["agent"])
    print(f"Contract request #{rid} recorded. Keep working with the current contract; the Integrator decides.")


def cmd_decide(args):
    me = whoami(args)

    def m(s):
        for r in s.get("requests", []):
            if r["id"] == args.id:
                r.update(status=args.decision, notes=args.notes or "", decided_at=now())
                return r
        raise BoardError(f"No contract request #{args.id}.")
    r = update(m, f"contract request #{args.id} {args.decision}", me["agent"])
    print(f"Request #{args.id} from {r['task']}: {args.decision}.")


def cmd_announce(args):
    me = whoami(args)
    fetch(force=True)
    main = rev(ref("main"))

    def m(s):
        s.setdefault("announcements", []).append({"text": args.text, "rebase": args.rebase, "main_sha": main, "at": now()})
    update(m, f"announcement: {args.text}", me["agent"])
    print("Announced." + (" Every active branch without this main commit will be told to rebase." if args.rebase else ""))


def cmd_ack(args):
    me = whoami(args)

    def m(s):
        if args.task not in s.setdefault("qa_ack", []):
            s["qa_ack"].append(args.task)
    update(m, f"QA handled merge of {args.task}", me["agent"])
    print(f"Acknowledged {args.task}.")


def main(argv=None):
    if hasattr(signal, "SIGPIPE"):  # behave quietly when piped into head/less
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252, which can't print the board
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--as", dest="as_", help="act as this agent (e.g. B-web, R, I) or 'human'")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("next", help="print your next action (agents run this constantly)")
    s.add_argument("--wait", type=int, default=0, help="keep polling up to N seconds while the answer is WAIT")
    s.add_argument("--interval", type=int, default=60)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_next)
    s = sub.add_parser("watch", help="print a line whenever your next action changes (for the Monitor tool)")
    s.add_argument("--interval", type=int, default=60)
    s.set_defaults(fn=cmd_watch)
    s = sub.add_parser("status", help="the whole board, for humans")
    s.add_argument("--all", action="store_true")
    s.add_argument("--log", type=int, default=8)
    s.set_defaults(fn=cmd_status)
    sub.add_parser("whoami").set_defaults(fn=cmd_whoami)
    s = sub.add_parser("init", help="Integrator, once, at Gate G0")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)
    for name, fn, hlp in (("start", cmd_start, "mark your task in progress"),
                          ("submit", cmd_submit, "ask for review of your pushed branch")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("task", nargs="?")
        s.set_defaults(fn=fn)
    s = sub.add_parser("review", help="Reviewer: record a verdict")
    s.add_argument("task")
    s.add_argument("verdict", choices=["approve", "changes"])
    s.add_argument("--notes")
    s.add_argument("--notes-file")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("signoff", help="consumer: record a sign-off")
    s.add_argument("task")
    s.add_argument("verdict", choices=["ok", "fail"])
    s.add_argument("--notes")
    s.add_argument("--notes-file")
    s.set_defaults(fn=cmd_signoff)
    s = sub.add_parser("merged", help="Integrator: record a merge")
    s.add_argument("task")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_merged)
    s = sub.add_parser("done", help="mark a main-branch or human task done (T00, T01, T20, T35, H0-H4)")
    s.add_argument("task")
    s.set_defaults(fn=cmd_done)
    s = sub.add_parser("block", help="mark your task blocked")
    s.add_argument("--on", required=True, help="task IDs, comma-separated, or a short reason")
    s.add_argument("--notes")
    s.add_argument("task", nargs="?")
    s.set_defaults(fn=cmd_block)
    s = sub.add_parser("unblock")
    s.add_argument("task", nargs="?")
    s.set_defaults(fn=cmd_unblock)
    s = sub.add_parser("request", help="file a contract request")
    s.add_argument("--file", required=True)
    s.add_argument("--summary", required=True)
    s.add_argument("task", nargs="?")
    s.set_defaults(fn=cmd_request)
    s = sub.add_parser("decide", help="Integrator: decide a contract request")
    s.add_argument("id", type=int)
    s.add_argument("decision", choices=["accept", "reject"])
    s.add_argument("--notes")
    s.set_defaults(fn=cmd_decide)
    s = sub.add_parser("announce", help="Integrator: tell everyone something (--rebase makes active branches rebase)")
    s.add_argument("text")
    s.add_argument("--rebase", action="store_true")
    s.set_defaults(fn=cmd_announce)
    s = sub.add_parser("ack", help="QA: mark a merge as handled")
    s.add_argument("task")
    s.set_defaults(fn=cmd_ack)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except BoardError as e:
        print(f"board: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
