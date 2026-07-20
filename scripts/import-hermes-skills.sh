#!/usr/bin/env bash
# Import curated Hermes skills into a Tango channel skills/ directory (playbook text only).
#
# Usage:
#   import-hermes-skills.sh <CHANNEL_ID> [skill_name ...]
#   import-hermes-skills.sh <CHANNEL_ID> coworker   # curated Slack-safe pack
#
# Env:
#   HERMES_HOME  (default /root/.hermes)
#   TANGO_DATA   (default /opt/apps/open-claude-tag/data)
set -euo pipefail

CHANNEL_ID="${1:?channel id required}"
shift || true

# Curated Slack-safe playbooks — no computer-use / DB / personal finance / host deploy.
COWORKER_PACK=(
  humanizer
  software-development-toolkit
  research-toolkit
  diagramming
  creative-ideation
  github
  cron-debug-path-issues
  migration-completion-checklist
  self-hosted-app-assessment
  production-operations
  production-monitoring
  project-context-first
  marketing-skills
  seo-audit
  social-content
  indie-growth-panel
  linkedin-content-ops
  nya-operations
  inksy-operations
  wisprs-seo-engine
  crawlr-ingestion
)

SKILLS=("$@")
if [[ ${#SKILLS[@]} -eq 0 ]]; then
  SKILLS=(coworker)
fi
if [[ ${#SKILLS[@]} -eq 1 && "${SKILLS[0]}" == "coworker" ]]; then
  SKILLS=("${COWORKER_PACK[@]}")
fi

HERMES_SKILLS="${HERMES_HOME:-/root/.hermes}/skills"
DEST="${TANGO_DATA:-/opt/apps/open-claude-tag/data}/channels/${CHANNEL_ID}/skills"
mkdir -p "$DEST"

_find_skill() {
  local name="$1"
  local src=""
  if [[ -f "$HERMES_SKILLS/$name/SKILL.md" ]]; then
    echo "$HERMES_SKILLS/$name/SKILL.md"
    return 0
  fi
  if [[ -f "$HERMES_SKILLS/$name.md" ]]; then
    echo "$HERMES_SKILLS/$name.md"
    return 0
  fi
  # Prefer shallowest non-archive match
  src=$(find "$HERMES_SKILLS" -type f -name SKILL.md \
    ! -path '*/.archive/*' \
    ! -path '*/._*' \
    \( -path "*/$name/SKILL.md" -o -path "*/$name/*/SKILL.md" \) \
    2>/dev/null | awk '{ print length, $0 }' | sort -n | head -1 | cut -d' ' -f2- || true)
  if [[ -n "$src" && -f "$src" ]]; then
    echo "$src"
    return 0
  fi
  # Fallback: directory named exactly $name anywhere
  src=$(find "$HERMES_SKILLS" -type f -path "*/$name/SKILL.md" \
    ! -path '*/.archive/*' 2>/dev/null | head -1 || true)
  echo "$src"
}

# Short trigger-rich overrides so NL matching stays sharp (no import boilerplate).
_desc_override() {
  case "$1" in
    humanizer)
      echo "Humanize text: strip AI-isms, buzzwords, and corporate tone; rewrite in a natural human voice."
      ;;
    seo-audit)
      echo "Audit or diagnose SEO issues, rankings, on-page SEO, meta tags, technical SEO health."
      ;;
    social-content)
      echo "Create or optimize social posts for LinkedIn, Twitter/X, Instagram, TikTok, content calendars."
      ;;
    github)
      echo "GitHub operations via gh: repos, PRs, code review, issues, analytics."
      ;;
    standup-notes)
      echo "Turn messy channel chatter into a short standup summary."
      ;;
    creative-ideation|ideation)
      echo "Generate project ideas via creative constraints."
      ;;
    *)
      return 1
      ;;
  esac
}

_extract_description() {
  local file="$1"
  local name="$2"
  local desc
  if desc="$(_desc_override "$name")"; then
    echo "$desc"
    return 0
  fi
  desc=$(awk '
    BEGIN { in_fm=0 }
    /^---[[:space:]]*$/ { if (++in_fm==2) exit; next }
    in_fm==1 && /^description:[[:space:]]*/ {
      sub(/^description:[[:space:]]*/, "")
      gsub(/^["'\'']|["'\'']$/, "")
      print
      exit
    }
  ' "$file" 2>/dev/null || true)
  if [[ -z "${desc:-}" ]]; then
    desc="Playbook for ${name}"
  fi
  # Keep single-line; do not append Hermes boilerplate (hurts skill matching)
  echo "$desc" | tr '\n' ' ' | sed 's/[[:space:]]*$//' | cut -c1-220
}

for name in "${SKILLS[@]}"; do
  src="$(_find_skill "$name")"
  if [[ -z "$src" || ! -f "$src" ]]; then
    echo "skip: $name (not found under $HERMES_SKILLS)"
    continue
  fi
  desc="$(_extract_description "$src" "$name")"
  {
    echo "---"
    echo "name: $name"
    echo "description: $desc"
    echo "status: active"
    echo "---"
    echo ""
    echo "> Tango import: playbook text only. Do **not** run host shell/DB/SSH steps directly."
    echo "> For Contabo power tasks, confirm with the requester then call \`hermes_ask\`."
    echo ""
    # Strip leading YAML frontmatter from source to avoid double frontmatter confusion
    awk '
      BEGIN { fm=0; started=0 }
      /^---[[:space:]]*$/ {
        if (fm==0) { fm=1; next }
        if (fm==1) { fm=2; next }
      }
      fm==1 { next }
      { started=1; print }
    ' "$src"
  } > "$DEST/${name}.md"
  echo "imported: $name <- $src"
done

echo "done: ${DEST}"
