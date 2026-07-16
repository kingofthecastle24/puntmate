#!/usr/bin/env bash
# git_push_retry.sh — commit staged changes (if any) and push, retrying with
# a fetch + rebase onto origin/main if the push is rejected because the
# remote moved (e.g. an interactive development push landing on main at the
# same moment a scheduled workflow run tries to commit its generated
# ledger/review-package data). Without this, a plain `git push` hard-fails
# the whole job on any concurrent write to main — which is exactly the
# failure Micah hit in production.
#
# Usage: git_push_retry.sh "<commit message>" [--soft]
#   --soft   On final failure (retries exhausted or a real rebase conflict),
#            print a ::warning:: and exit 0 instead of failing the job. Use
#            this for steps that were already documented as non-fatal
#            (bookkeeping-only commits where the primary action already
#            happened, e.g. publish/rejection records).
#            Without --soft, final failure is a hard job failure — used for
#            the ledger/review-package commit, since that data genuinely
#            needs to land on main for the approval step to work.
#
# Assumes the caller has already run `git add` for whatever paths it wants
# committed, and that the working directory is the repo root.

set -uo pipefail

COMMIT_MSG="${1:?commit message required}"
SOFT=false
if [ "${2:-}" = "--soft" ]; then
  SOFT=true
fi

git config user.name  "PuntMate Bot"
git config user.email "puntmatenz@gmail.com"

if git diff --staged --quiet; then
  echo "Nothing to commit."
  exit 0
fi

git commit -m "$COMMIT_MSG"

MAX_ATTEMPTS=5
attempt=0
until git push; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    if [ "$SOFT" = true ]; then
      echo "::warning::git push failed after $MAX_ATTEMPTS attempts (concurrent push to main) — giving up. Non-fatal for this step; the underlying action already happened."
      exit 0
    fi
    echo "::error::git push failed after $MAX_ATTEMPTS attempts (concurrent push to main) — giving up. This run's generated data is committed locally but was NOT pushed to main."
    exit 1
  fi
  echo "::warning::git push rejected (attempt $attempt/$MAX_ATTEMPTS) — remote has commits we don't have locally (likely a concurrent push to main). Fetching + rebasing and retrying..."
  sleep $((attempt * 5))
  git fetch origin main
  if ! git rebase origin/main; then
    echo "::error::git rebase onto origin/main hit a real conflict — cannot auto-resolve."
    git rebase --abort || true
    if [ "$SOFT" = true ]; then
      echo "::warning::Rebase conflict — giving up. Non-fatal for this step."
      exit 0
    fi
    exit 1
  fi
done

if [ "$attempt" -gt 0 ]; then
  echo "Pushed successfully after $attempt retry attempt(s)."
else
  echo "Pushed successfully."
fi
