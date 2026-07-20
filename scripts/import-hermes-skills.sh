#!/usr/bin/env bash
# Import curated Hermes skills into a Tango channel skills/ directory (playbook text only).
# Usage: import-hermes-skills.sh <CHANNEL_ID> [skill_name ...]
# Default skills: devops github data-science
set -euo pipefail

CHANNEL_ID="${1:?channel id required}"
shift || true
SKILLS=("$@")
if [[ ${#SKILLS[@]} -eq 0 ]]; then
  SKILLS=(devops github data-science)
fi

HERMES_SKILLS="${HERMES_HOME:-/root/.hermes}/skills"
DEST="${TANGO_DATA:-/opt/apps/open-claude-tag/data}/channels/${CHANNEL_ID}/skills"
mkdir -p "$DEST"

for name in "${SKILLS[@]}"; do
  src=""
  if [[ -f "$HERMES_SKILLS/$name/SKILL.md" ]]; then
    src="$HERMES_SKILLS/$name/SKILL.md"
  elif [[ -f "$HERMES_SKILLS/$name.md" ]]; then
    src="$HERMES_SKILLS/$name.md"
  else
    # search one level of categories
    found=$(find "$HERMES_SKILLS" -type f -path "*/$name/SKILL.md" 2>/dev/null | head -1 || true)
    src="$found"
  fi
  if [[ -z "$src" || ! -f "$src" ]]; then
    echo "skip: $name (not found under $HERMES_SKILLS)"
    continue
  fi
  # Flatten to single markdown file; ensure name frontmatter
  {
    echo "---"
    echo "name: $name"
    echo "description: Imported from Hermes skill $name (playbook only)"
    echo "status: active"
    echo "---"
    echo ""
    cat "$src"
  } > "$DEST/${name}.md"
  echo "imported: $name -> $DEST/${name}.md"
done
