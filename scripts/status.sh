#!/usr/bin/env bash
# Kept for muscle memory: the board is the source of truth now.
exec python3 "$(git rev-parse --show-toplevel)/scripts/board.py" status "$@"
