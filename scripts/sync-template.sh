#!/usr/bin/env bash
# sync-template.sh
# Surgically applies missing v1.1.0 template changes to a project repo.
# Only modifies what's actually missing — no file overwrites.
# Creates a branch, commits, and pushes — user creates the PR.
#
# Usage:
#   ./scripts/sync-template.sh <target>              # apply and push
#   ./scripts/sync-template.sh <target> --dry-run     # preview only
#
#   target: /path/to/repo (local) or git clone URL (remote)
#
# Requirements: git

set -euo pipefail

TEMPLATE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE_VERSION=$(cat "$TEMPLATE_DIR/VERSION")
BRANCH_NAME="chore/template-sync-v${TEMPLATE_VERSION}"

usage() {
  cat <<EOF
Usage: $(basename "$0") <target> [--dry-run]

  target      /path/to/repo (local) or git clone URL (remote)

Applies missing v${TEMPLATE_VERSION} changes surgically.
Creates branch '${BRANCH_NAME}', commits, and pushes.

Options:
  --dry-run   Show what would change without committing or pushing

Requires: git
EOF
  exit 1
}

# ── Args ─────────────────────────────────────────────────────────────
[[ $# -lt 1 ]] && usage

TARGET="$1"
DRY_RUN=false
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=true

# ── Resolve target directory ─────────────────────────────────────────
CLEANUP_WORKDIR=""

if [[ -d "$TARGET" ]]; then
  TARGET_DIR="$(cd "$TARGET" && pwd)"
  REPO_LABEL="$(basename "$TARGET_DIR")"
  if [[ ! -d "$TARGET_DIR/.git" ]]; then
    echo "ERROR: $TARGET_DIR is not a git repository."
    exit 1
  fi
else
  WORKDIR=$(mktemp -d)
  CLEANUP_WORKDIR="$WORKDIR"
  TARGET_DIR="$WORKDIR/target"
  REPO_LABEL="$TARGET"
  echo "==> Cloning $TARGET into temp directory..."
  git clone --depth=50 "$TARGET" "$TARGET_DIR"
fi

cleanup() { [[ -n "$CLEANUP_WORKDIR" ]] && rm -rf "$CLEANUP_WORKDIR"; }
trap cleanup EXIT

cd "$TARGET_DIR"

# ── Check current version ────────────────────────────────────────────
CURRENT_VERSION="0.0.0"
[[ -f VERSION ]] && CURRENT_VERSION=$(cat VERSION)

if [[ "$CURRENT_VERSION" == "$TEMPLATE_VERSION" ]]; then
  echo "==> $REPO_LABEL already at template v${TEMPLATE_VERSION}. Nothing to do."
  exit 0
fi

echo "==> $REPO_LABEL: v$CURRENT_VERSION -> v$TEMPLATE_VERSION"

# ── Ensure clean working tree ────────────────────────────────────────
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: Working tree is not clean. Commit or stash changes first."
  exit 1
fi

# ── Check if branch already exists ───────────────────────────────────
if git show-ref --verify --quiet "refs/heads/$BRANCH_NAME" 2>/dev/null; then
  echo "ERROR: Local branch '$BRANCH_NAME' already exists."
  exit 1
fi
if git ls-remote --heads origin "$BRANCH_NAME" 2>/dev/null | grep -q "$BRANCH_NAME"; then
  echo "ERROR: Remote branch '$BRANCH_NAME' already exists."
  exit 1
fi

# ── Create branch ────────────────────────────────────────────────────
git checkout -b "$BRANCH_NAME"

# ── Apply missing changes ────────────────────────────────────────────
CHANGES=()

# --- 1. VERSION file ---
if [[ ! -f VERSION ]] || [[ "$(cat VERSION)" != "$TEMPLATE_VERSION" ]]; then
  echo "$TEMPLATE_VERSION" > VERSION
  CHANGES+=("add VERSION ($TEMPLATE_VERSION)")
  echo "  + VERSION"
fi

# --- 2. memory/MEMORY.md ---
if [[ ! -f memory/MEMORY.md ]]; then
  mkdir -p memory
  cp "$TEMPLATE_DIR/memory/MEMORY.md" memory/MEMORY.md
  CHANGES+=("add memory/MEMORY.md")
  echo "  + memory/MEMORY.md"
fi

# --- 4. .gitignore with settings.local.json ---
if [[ ! -f .gitignore ]]; then
  echo ".claude/settings.local.json" > .gitignore
  CHANGES+=("add .gitignore")
  echo "  + .gitignore"
elif ! grep -q 'settings.local.json' .gitignore; then
  echo "" >> .gitignore
  echo ".claude/settings.local.json" >> .gitignore
  CHANGES+=("append settings.local.json to .gitignore")
  echo "  ~ .gitignore (appended entry)"
fi

# --- 5. Memory section in instructions.md ---
if [[ -f .agent/instructions.md ]] && ! grep -q '## Memory' .agent/instructions.md; then
  # Find insertion point: before "## When unsure" or "## Never do", or append at end
  MEMORY_BLOCK='## Memory
- Use `memory/` as the sole memory location for all persistent context.
- Do NOT use the default Claude memory directory (~/.claude/projects/.../memory/).
- Memory index lives at `memory/MEMORY.md`.
- Write new memories as individual .md files inside `memory/` with frontmatter (name, description, type).
- Update `memory/MEMORY.md` as a one-line-per-entry index.
- Memory types: user, feedback, project, reference.
- Session notes go in `memory/sessions/YYYY-MM-DD.md`.
- Quick tasks go in `memory/quick-tasks.md`.'

  if grep -q '## When unsure' .agent/instructions.md; then
    # Insert before "## When unsure"
    sed -i '' "/^## When unsure/i\\
\\
${MEMORY_BLOCK//
/\\
}\\
" .agent/instructions.md
    CHANGES+=("add Memory section to instructions.md (before 'When unsure')")
    echo "  ~ .agent/instructions.md (added Memory section)"
  elif grep -q '## Never do' .agent/instructions.md; then
    # Insert before "## Never do"
    sed -i '' "/^## Never do/i\\
\\
${MEMORY_BLOCK//
/\\
}\\
" .agent/instructions.md
    CHANGES+=("add Memory section to instructions.md (before 'Never do')")
    echo "  ~ .agent/instructions.md (added Memory section)"
  else
    # Append at end
    printf '\n%s\n' "$MEMORY_BLOCK" >> .agent/instructions.md
    CHANGES+=("add Memory section to instructions.md (appended)")
    echo "  ~ .agent/instructions.md (added Memory section)"
  fi
fi

# --- 6. Remove env vars from context-update.yml ---
if [[ -f .github/workflows/context-update.yml ]] && grep -qE 'JIRA_PROJECT_KEY|PROJECT_NAME' .github/workflows/context-update.yml; then
  # Remove lines containing JIRA_PROJECT_KEY or PROJECT_NAME (separate passes for BSD sed)
  sed -i '' '/JIRA_PROJECT_KEY/d' .github/workflows/context-update.yml
  sed -i '' '/PROJECT_NAME/d' .github/workflows/context-update.yml

  # Remove the now-empty env: block (env: followed by blank or non-indented line)
  sed -i '' '/^[[:space:]]*env:[[:space:]]*$/{
    N
    /env:[[:space:]]*\n[[:space:]]*$/d
    /env:[[:space:]]*\n[[:space:]]*-/d
  }' .github/workflows/context-update.yml

  # Clean up any resulting double blank lines
  sed -i '' '/^$/N;/^\n$/d' .github/workflows/context-update.yml

  CHANGES+=("remove env var pass-through from context-update.yml")
  echo "  ~ .github/workflows/context-update.yml (removed env vars)"
fi

# --- 7. Replace JIRA/Linear footer with Memory footer in generate-context.py ---
if [[ -f scripts/generate-context.py ]] && ! grep -q 'Memory: memory/MEMORY.md' scripts/generate-context.py; then
  if grep -q 'JIRA project:' scripts/generate-context.py; then
    sed -i '' 's|- JIRA project: {JIRA_KEY}|- Memory: memory/MEMORY.md (do NOT use ~/.claude/ memory)|' scripts/generate-context.py
    CHANGES+=("replace JIRA footer with Memory footer in generate-context.py")
    echo "  ~ scripts/generate-context.py (JIRA -> Memory footer)"
  elif grep -q 'Linear team:' scripts/generate-context.py; then
    sed -i '' '/- Linear team:/s|.*|- Memory: memory/MEMORY.md (do NOT use ~/.claude/ memory)|' scripts/generate-context.py
    CHANGES+=("replace Linear footer with Memory footer in generate-context.py")
    echo "  ~ scripts/generate-context.py (Linear -> Memory footer)"
  fi
fi

# --- 8. Remove "Set GitHub repo variables" from README.md ---
if [[ -f README.md ]] && grep -qi 'GitHub repo variables\|Set repo variables' README.md; then
  sed -i '' '/Set.*GitHub repo variables\|Set repo variables/d' README.md
  CHANGES+=("remove 'Set repo variables' step from README.md")
  echo "  ~ README.md (removed 'Set repo variables' step)"
fi

# ── Report ───────────────────────────────────────────────────────────
echo ""
if [[ ${#CHANGES[@]} -eq 0 ]]; then
  echo "==> All v${TEMPLATE_VERSION} changes already applied. Nothing to do."
  git checkout -- . 2>/dev/null
  git clean -fd 2>/dev/null
  git checkout - 2>/dev/null
  git branch -D "$BRANCH_NAME" 2>/dev/null
  exit 0
fi

echo "==> ${#CHANGES[@]} change(s) to apply:"
for c in "${CHANGES[@]}"; do
  echo "    - $c"
done

if $DRY_RUN; then
  echo ""
  echo "==> Diff preview:"
  git add -A
  git diff --cached --stat
  echo ""
  git diff --cached
  echo ""
  echo "==> Dry run complete. No changes made."
  git reset HEAD -- . >/dev/null 2>&1
  git checkout -- . 2>/dev/null
  git clean -fd >/dev/null 2>&1
  git checkout - 2>/dev/null
  git branch -D "$BRANCH_NAME" 2>/dev/null
  exit 0
fi

# ── Commit and push ──────────────────────────────────────────────────
git add -A
git commit -m "$(cat <<EOF
chore: sync template to v${TEMPLATE_VERSION}

Applies missing v${TEMPLATE_VERSION} changes from agentic-workspace-template.
See CHANGELOG.md for what changed in this version.

Changes applied:
$(printf '  - %s\n' "${CHANGES[@]}")
EOF
)"

git push -u origin "$BRANCH_NAME"

echo ""
echo "==> Done! Branch '$BRANCH_NAME' pushed for $REPO_LABEL."
