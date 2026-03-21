#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
DIST="$REPO_ROOT/site/dist"
WORKTREE="$(mktemp -d)"

if git show-ref --verify --quiet refs/heads/gh-pages; then
    git worktree add "$WORKTREE" gh-pages
else
    git worktree add --orphan -b gh-pages "$WORKTREE"
fi

cleanup() {
    git worktree remove --force "$WORKTREE" 2>/dev/null
    rm -rf "$WORKTREE"
}
trap cleanup EXIT

cp -r "$DIST/." "$WORKTREE/"
cd "$WORKTREE"
git add -A

if git diff --cached --quiet; then
    echo "Nothing to deploy, site is up to date."
    exit 0
fi

git commit -m "Deploy $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push origin gh-pages --force
echo "Deployed to gh-pages."
