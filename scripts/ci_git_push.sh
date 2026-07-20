#!/usr/bin/env bash
# Commit (optional) and push with conflict-aware retries for concurrent CI writers.
#
# Generated artifacts (DB, snapshot, briefs) prefer this job's versions on conflict.
# Append-only *.jsonl files are line-merged so concurrent appends are preserved.
#
# Usage:
#   bash scripts/ci_git_push.sh --message "chore: ..." -- [paths...]
#   bash scripts/ci_git_push.sh --message "chore: ..." --add-if-exists path1 path2 -- path3
#
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

set_output() {
  local key="$1"
  local value="$2"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "${key}=${value}" >> "$GITHUB_OUTPUT"
  fi
}

merge_jsonl() {
  # Keep remote lines, then append any lines from ours that are not already present.
  local path="$1"
  local ours_commit="$2"
  local tmp_ours tmp_remote
  tmp_ours="$(mktemp)"
  tmp_remote="$(mktemp)"
  if git show "${ours_commit}:${path}" >"$tmp_ours" 2>/dev/null; then
    :
  else
    rm -f "$tmp_ours" "$tmp_remote"
    return 0
  fi
  if [[ -f "$path" ]]; then
    cp "$path" "$tmp_remote"
  else
    : >"$tmp_remote"
  fi
  python3 - "$tmp_remote" "$tmp_ours" "$path" <<'PY'
import sys
from pathlib import Path

remote_path, ours_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
remote = Path(remote_path).read_text(encoding="utf-8").splitlines()
ours = Path(ours_path).read_text(encoding="utf-8").splitlines()
seen = set(remote)
out = list(remote)
for line in ours:
    if line and line not in seen:
        out.append(line)
        seen.add(line)
Path(out_path).write_text(("\n".join(out) + ("\n" if out else "")), encoding="utf-8")
PY
  rm -f "$tmp_ours" "$tmp_remote"
}

recover_from_conflict() {
  local ours_commit="$1"
  echo "Rebase conflict — recovering by overlaying this job's artifacts onto origin/main..."
  git rebase --abort 2>/dev/null || true
  git fetch origin main
  git reset --hard origin/main

  local files=()
  while IFS= read -r f; do
    [[ -n "$f" ]] && files+=("$f")
  done < <(git diff-tree --no-commit-id --name-only -r "$ours_commit")

  if ((${#files[@]} == 0)); then
    echo "No files in local commit after sync."
    return 1
  fi

  local f
  for f in "${files[@]}"; do
    if [[ "$f" == *.jsonl ]]; then
      merge_jsonl "$f" "$ours_commit"
      git add -- "$f" 2>/dev/null || true
    else
      if git checkout "$ours_commit" -- "$f" 2>/dev/null; then
        git add -- "$f"
      fi
    fi
  done

  if git diff --staged --quiet; then
    echo "Remote already contains equivalent changes."
    return 1
  fi
  git commit -m "$MESSAGE"
  return 0
}

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
  set_output committed false
  exit 0
fi

git commit -m "$MESSAGE"

MAX_ATTEMPTS=5
attempt=1
while true; do
  if git push origin HEAD; then
    echo "Push succeeded."
    set_output committed true
    exit 0
  fi

  if (( attempt >= MAX_ATTEMPTS )); then
    echo "Push failed after ${MAX_ATTEMPTS} attempts." >&2
    set_output committed false
    exit 1
  fi

  echo "Push rejected (attempt ${attempt}/${MAX_ATTEMPTS}); syncing with origin/main..."
  git fetch origin main
  OUR_COMMIT="$(git rev-parse HEAD)"
  if git rebase origin/main; then
    echo "Rebase succeeded; retrying push..."
  else
    if ! recover_from_conflict "$OUR_COMMIT"; then
      echo "Nothing to push after conflict recovery." >&2
      set_output committed false
      exit 0
    fi
  fi
  attempt=$((attempt + 1))
  sleep $((attempt * 2))
done
