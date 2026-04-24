#!/usr/bin/env bash
set -euo pipefail

# Configurable
BASE_BRANCH="${BASE_BRANCH:-main}"
PH3_BRANCH="feature/phase3-multi"
PH4_BRANCH="feature/phase4-logging"

PH3_BODY_FILE="${PH3_BODY_FILE:-phase3_pr_body.txt}"
PH4_BODY_FILE="${PH4_BODY_FILE:-phase4_pr_body.txt}"

# Resolve owner/repo from origin URL
OWNER=""
REPO=""
REPO_URL=$(git remote get-url origin 2>/dev/null || true)
if [[ -n "$REPO_URL" ]]; then
  if [[ "$REPO_URL" =~ git@github.com:(.*)/(.*).git ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
  elif [[ "$REPO_URL" =~ https://github.com/(.*)/(.*).git ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
  fi
fi

# PR bodies (read from files if present, else fall back)
if [[ -f "$PH3_BODY_FILE" ]]; then
  PH3_BODY_CONTENT=$(cat "$PH3_BODY_FILE")
else
  PH3_BODY_CONTENT="Phase 3 scaffold PR prepared by automation. See phase3_pr_body.txt for details."
fi

if [[ -f "$PH4_BODY_FILE" ]]; then
  PH4_BODY_CONTENT=$(cat "$PH4_BODY_FILE")
else
  PH4_BODY_CONTENT="Phase 4 scaffold PR prepared by automation. See phase4_pr_body.txt for details."
fi

echo "Pushing branches..."
git fetch --all --prune
git push -u origin "$PH3_BRANCH"
git push -u origin "$PH4_BRANCH"

# Try gh first
if command -v gh >/dev/null 2>&1; then
  if gh --version >/dev/null 2>&1; then
    echo "Creating PRs using gh..."
    gh pr create --base "$BASE_BRANCH" --head "$PH3_BRANCH" --title "Phase 3: Multi-Device Orchestration and Inventory Parsing" --body "$PH3_BODY_CONTENT"
    gh pr create --base "$BASE_BRANCH" --head "$PH4_BRANCH" --title "Phase 4: Fleet Logging and Per-Host Logs" --body "$PH4_BODY_CONTENT"
    exit 0
  fi
fi

# Fallback to REST API with a PAT
TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [[ -z "$TOKEN" ]]; then
  echo "No GitHub token found. Set GITHUB_TOKEN or GH_TOKEN to use REST API path." >&2
  exit 1
fi

if [[ -z "$OWNER" || -z "$REPO" ]]; then
  echo "Cannot determine owner/repo from git remote. Set OWNER/REPO or ensure origin URL is accessible." >&2
  exit 1
fi

# Helper to escape body content for JSON
escape_json() {
  python3 - << 'PY'
import json,sys
text = sys.stdin.read()
print(json.dumps(text))
PY
}

BODY3_ESCAPED=$(printf '%s' "$PH3_BODY_CONTENT" | escape_json)
BODY4_ESCAPED=$(printf '%s' "$PH4_BODY_CONTENT" | escape_json)

PR3_JSON=$(printf '{"title": "%s", "head": "%s", "base": "%s", "body": %s}' \
  "Phase 3: Multi-Device Orchestration and Inventory Parsing" "$PH3_BRANCH" "$BASE_BRANCH" "$BODY3_ESCAPED")

PR4_JSON=$(printf '{"title": "%s", "head": "%s", "base": "%s", "body": %s}' \
  "Phase 4: Fleet Logging and Per-Host Logs" "$PH4_BRANCH" "$BASE_BRANCH" "$BODY4_ESCAPED")

API_URL="https://api.github.com/repos/$OWNER/$REPO/pulls"

echo "Creating Phase 3 PR via REST API..."
curl -s -X POST -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" \
  "$API_URL" -d "$PR3_JSON" | head -n 2

echo "Creating Phase 4 PR via REST API..."
curl -s -X POST -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" \
  "$API_URL" -d "$PR4_JSON" | head -n 2

echo "Done."