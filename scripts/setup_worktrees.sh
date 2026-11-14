#!/usr/bin/env bash
# Create git worktrees for parallel Claude Code agents.
#
# Run from anywhere inside the repo, after Gate G0 is merged to main.
#
#   scripts/setup_worktrees.sh wave1          # T10-T16, T18, T19 + review worktrees
#   scripts/setup_worktrees.sh wave2          # T21-T26 (T20 runs on main)
#   scripts/setup_worktrees.sh wave3          # T30-T33
#   scripts/setup_worktrees.sh add T17 input  # one task, fresh from main
#   scripts/setup_worktrees.sh review         # ../<repo>-review (detached) and ../<repo>-reviews (branch "reviews")
#   scripts/setup_worktrees.sh list
#   scripts/setup_worktrees.sh remove T10     # after the task is merged
#
# Each worktree gets:
#   - branch feat/<TASK>-<slug> from $BASE (default: main)
#   - .env.worktree with P2D_TASK and per-task ports (API 8000+N, web 5173+N, N = task number)
#   - a symlink to the main checkout's .env (secrets stay out of git)
#   - uv sync and npm ci (set SKIP_NPM=1 to skip npm for non-frontend tasks)
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PARENT="$(dirname "$ROOT")"
NAME="$(basename "$ROOT")"
BASE="${BASE:-main}"

port_offset() {                       # T10 -> 10, T34b -> 84 (b adds 50 so T34a/T34b don't collide)
  local id="$1" n
  n="$(echo "$id" | tr -cd '0-9')"
  n=$((10#$n))
  [[ "$id" == *b ]] && n=$((n + 50))
  echo "$n"
}

install_deps() {
  local dir="$1"
  (cd "$dir" && uv sync --quiet)
  if [[ "${SKIP_NPM:-0}" != "1" && -f "$dir/frontend/package.json" ]]; then
    (cd "$dir/frontend" && npm ci --silent)
  fi
}

write_env() {
  local dir="$1" id="$2" n="$3"
  cat > "$dir/.env.worktree" <<EOF
P2D_TASK=$id
API_PORT=$((8000 + n))
WEB_PORT=$((5173 + n))
P2D_RUNS_DIR=$dir/runs
EOF
  if [[ -f "$ROOT/.env" ]]; then ln -sf "$ROOT/.env" "$dir/.env"; fi
}

add_task() {
  local id="$1" slug="$2"
  local dir="$PARENT/$NAME-$id-$slug" branch="feat/$id-$slug" n
  n="$(port_offset "$id")"
  if [[ -d "$dir" ]]; then
    echo "skip   $id  ($dir already exists)"
    return
  fi
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    git worktree add "$dir" "$branch"
  else
    git worktree add -b "$branch" "$dir" "$BASE"
  fi
  write_env "$dir" "$id" "$n"
  install_deps "$dir"
  echo "ready  $id  $dir  branch=$branch  api=$((8000 + n)) web=$((5173 + n))"
}

add_review() {
  local rdir="$PARENT/$NAME-review" ndir="$PARENT/$NAME-reviews"
  if [[ ! -d "$rdir" ]]; then
    git worktree add --detach "$rdir" "$BASE"
    write_env "$rdir" "R" 99
    install_deps "$rdir"
    echo "ready  R    $rdir  (detached; check out branches with git checkout --detach <branch>)"
  fi
  if [[ ! -d "$ndir" ]]; then
    if git show-ref --verify --quiet refs/heads/reviews; then
      git worktree add "$ndir" reviews
    else
      git worktree add -b reviews "$ndir" "$BASE"
    fi
    mkdir -p "$ndir/handoff/reviews"
    echo "ready  R    $ndir  (branch reviews: write handoff/reviews/<TASK>.md here)"
  fi
}

case "${1:-}" in
  wave1)
    add_task T10 validators
    add_task T11 cad
    add_task T12 firmware
    add_task T13 agent
    add_task T14 api
    add_task T15 web
    add_task T16 bom
    add_task T18 parts
    add_task T19 qa
    add_review
    ;;
  wave2)
    add_task T21 cross-checks
    add_task T22 edits
    add_task T23 snippets
    add_task T24 web-live
    add_task T25 assembly
    add_task T26 simulation
    ;;
  wave3)
    add_task T30 evals
    add_task T31 device
    add_task T32 web-explain
    add_task T33 docs
    ;;
  add)
    [[ $# -eq 3 ]] || { echo "usage: $0 add <TASK> <slug>"; exit 1; }
    add_task "$2" "$3"
    ;;
  review)
    add_review
    ;;
  list)
    git worktree list
    ;;
  remove)
    [[ $# -eq 2 ]] || { echo "usage: $0 remove <TASK>"; exit 1; }
    for d in "$PARENT/$NAME-$2-"*; do
      [[ -d "$d" ]] || continue
      # Refuse if there is real work left; ignore files this script created.
      dirty="$(git -C "$d" status --porcelain | grep -vE '^\?\? (\.env|\.env\.worktree)$' || true)"
      if [[ -n "$dirty" ]]; then
        echo "refuse $d has uncommitted changes:"; echo "$dirty"; continue
      fi
      git worktree remove --force "$d"
      echo "removed $d (branch kept; delete it with git branch -d once merged)"
    done
    ;;
  *)
    sed -n '2,20p' "$0"
    exit 1
    ;;
esac
