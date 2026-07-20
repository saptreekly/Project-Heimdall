#!/usr/bin/env bash
# Commit (optional) and push with rebase retries for concurrent CI writers.
#
# Usage:
#   bash scripts/ci_git_push.sh --message "chore: ..." -- [paths...]
#   bash scripts/ci_git_push.sh --message "chore: ..." --add-if-exists path1 path2 -- path3
#
# Always runs: git add for required paths, optional exists-only paths, then commit+push.
# Sets GITHUB_OUTPUT committed=true|false when available.

set -euo pipefail

MESSAGE=""
REQUIRED=()
OPTIONAL=()
MODE="required"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --message)
      MESSAGE="${2:-}"
      shift 2
      ;;
    --add-if-exists)
      MODE="optional"
      shift
      ;;
    --)
      MODE="required"
      shift
      ;;
    *)
      if [[ "$MODE" == "optional" ]]; then
        OPTIONAL+=("$1")
      else
        REQUIRED+=("$1")
      fi
      shift
      ;;
  esac
done

if [[ -z "$MESSAGE" ]]; then
  echo "ci_git_push.sh: --message is required" >&2
  exit 2
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if ((${#REQUIRED[@]})); then
  git add -- "${REQUIRED[@]}"
fi

for path in "${OPTIONAL[@]+"${OPTIONAL[@]}"}"; do
  if [[ -e "$path" ]]; then
    git add -- "$path"
  fi
done

if git diff --staged --quiet; then
  echo "No changes to commit."
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "committed=false" >> "$GITHUB_OUTPUT"
  fi
  exit 0
fi

git commit -m "$MESSAGE"

MAX_ATTEMPTS=5
attempt=1
while true; do
  if git push origin HEAD; then
    echo "Push succeeded."
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
      echo "committed=true" >> "$GITHUB_OUTPUT"
    fi
    exit 0
  fi

  if (( attempt >= MAX_ATTEMPTS )); then
    echo "Push failed after ${MAX_ATTEMPTS} attempts." >&2
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
      echo "committed=false" >> "$GITHUB_OUTPUT"
    fi
    exit 1
  fi

  echo "Push rejected (attempt ${attempt}/${MAX_ATTEMPTS}); rebasing onto origin/main..."
  git fetch origin main
  if ! git rebase origin/main; then
    echo "Rebase conflict — aborting." >&2
    git rebase --abort || true
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
      echo "committed=false" >> "$GITHUB_OUTPUT"
    fi
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep $((attempt))
done
