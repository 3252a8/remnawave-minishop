#!/usr/bin/env bash
set -euo pipefail

PRIMARY_REMOTE="${PRIMARY_REMOTE:-origin}"
MIRROR_REMOTE="${MIRROR_REMOTE:-gitlab}"
SYNC_BRANCHES="${SYNC_BRANCHES:-}"
SYNC_TAGS="${SYNC_TAGS:-true}"
FORCE="${FORCE:-false}"
PRUNE="${PRUNE:-false}"
DRY_RUN="${DRY_RUN:-false}"

usage() {
  cat <<'EOF'
Usage: scripts/sync-gitlab-mirror.sh [--force] [--prune] [--no-tags] [--dry-run]

Mirrors branches and tags from the primary GitHub remote to the GitLab backup remote.

Environment:
  PRIMARY_REMOTE  Primary remote name. Default: origin
  MIRROR_REMOTE   Mirror remote name. Default: gitlab
  SYNC_BRANCHES   Space/comma separated branch list. Default: all PRIMARY_REMOTE branches
  SYNC_TAGS       Push tags too. Default: true
  FORCE           Use --force-with-lease for branches. Default: false
  PRUNE           Delete GitLab branches missing on GitHub. Default: false
  DRY_RUN         Print git commands without running them. Default: false
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE="true" ;;
    --prune) PRUNE="true" ;;
    --no-tags) SYNC_TAGS="false" ;;
    --dry-run) DRY_RUN="true" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

run_git() {
  if [[ "$DRY_RUN" == "true" ]]; then
    printf 'git'
    printf ' %q' "$@"
    printf '\n'
    return
  fi

  git "$@"
}

normalize_list() {
  local value="$1"
  value="${value//,/ }"
  value="${value//;/ }"
  echo "$value"
}

run_git fetch "$PRIMARY_REMOTE" --prune --tags

if [[ "$FORCE" == "true" ]]; then
  run_git fetch "$MIRROR_REMOTE" --prune
fi

if [[ -n "$SYNC_BRANCHES" ]]; then
  read -r -a branches <<< "$(normalize_list "$SYNC_BRANCHES")"
else
  branches=()
  while IFS= read -r branch; do
    [[ "$branch" != "HEAD" ]] || continue
    branches+=("$branch")
  done < <(git for-each-ref --format='%(refname:strip=3)' "refs/remotes/$PRIMARY_REMOTE")
fi

for branch in "${branches[@]}"; do
  [[ -n "$branch" ]] || continue
  src="refs/remotes/$PRIMARY_REMOTE/$branch"
  dst="refs/heads/$branch"
  args=("push" "$MIRROR_REMOTE")
  if [[ "$FORCE" == "true" ]]; then
    args+=("--force-with-lease=$dst")
  fi
  args+=("$src:$dst")
  run_git "${args[@]}"
done

if [[ "$SYNC_TAGS" == "true" ]]; then
  run_git push "$MIRROR_REMOTE" --tags
fi

if [[ "$PRUNE" == "true" ]]; then
  primary_branches="$(printf '%s\n' "${branches[@]}")"
  while read -r mirror_branch; do
    [[ -n "$mirror_branch" ]] || continue
    if ! grep -Fxq "$mirror_branch" <<< "$primary_branches"; then
      run_git push "$MIRROR_REMOTE" ":refs/heads/$mirror_branch"
    fi
  done < <(git ls-remote --heads "$MIRROR_REMOTE" | sed 's#.*refs/heads/##')
fi
