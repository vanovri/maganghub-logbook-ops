#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${MAGANGHUB_LOGBOOK_OPS_REPO:-https://github.com/vanovri/maganghub-logbook-ops.git}"
INSTALL_HOME="${MAGANGHUB_LOGBOOK_OPS_HOME:-$HOME/.local/share/maganghub-logbook-ops}"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force|-f) FORCE=1 ;;
    --help|-h)
      echo "Usage: ./install.sh [--force]"
      echo "Installs the maganghub-logbook-ops skill into agent skill directories."
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

script_dir=""
src_script="${BASH_SOURCE[0]-}"
if [[ -n "$src_script" && -f "$src_script" ]]; then
  script_dir="$(cd "$(dirname "$src_script")" && pwd)"
fi

if [[ -n "$script_dir" && -f "$script_dir/skills/maganghub-logbook-ops/SKILL.md" ]]; then
  src="$script_dir/skills/maganghub-logbook-ops"
else
  if ! command -v git >/dev/null 2>&1; then
    echo "Error: git is required for remote installation." >&2
    exit 1
  fi
  if [[ -d "$INSTALL_HOME/.git" ]]; then
    git -C "$INSTALL_HOME" pull --ff-only
  else
    mkdir -p "$(dirname "$INSTALL_HOME")"
    rm -rf "$INSTALL_HOME"
    git clone --depth 1 "$REPO_URL" "$INSTALL_HOME"
  fi
  src="$INSTALL_HOME/skills/maganghub-logbook-ops"
fi

if [[ ! -f "$src/SKILL.md" || ! -f "$src/scripts/logbook_ops.py" ]]; then
  echo "Error: invalid skill package at $src" >&2
  exit 1
fi

targets=()
if [[ -n "${SKILL_TARGETS:-}" ]]; then
  IFS=':' read -r -a targets <<< "$SKILL_TARGETS"
else
  targets=("$HOME/.claude/skills" "$HOME/.agents/skills" "$HOME/.omp/agent/skills")
fi

for dir in "${targets[@]}"; do
  [[ -z "$dir" ]] && continue
  mkdir -p "$dir"
  dest="$dir/maganghub-logbook-ops"
  if [[ -e "$dest" && ! -L "$dest" ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
      rm -rf "$dest"
    else
      echo "Skipped $dest (regular directory exists; pass --force to replace)" >&2
      continue
    fi
  fi
  ln -sfn "$src" "$dest"
  echo "Linked $dest -> $src"
done

echo "Done! Invoke /maganghub-logbook-ops in your agent."
