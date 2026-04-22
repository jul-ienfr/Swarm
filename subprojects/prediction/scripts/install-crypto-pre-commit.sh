#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRIPT_PATH="$REPO_ROOT/subprojects/prediction/scripts/pre-commit-crypto.sh"
HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK_PATH="$HOOK_DIR/pre-commit"
BACKUP_PATH="$HOOK_DIR/pre-commit.hermes-backup"

mkdir -p "$HOOK_DIR"

if [[ ! -x "$SCRIPT_PATH" ]]; then
  chmod +x "$SCRIPT_PATH"
fi

if [[ -f "$HOOK_PATH" ]] && ! grep -q "BEGIN HERMES CRYPTO PRE-COMMIT" "$HOOK_PATH"; then
  cp "$HOOK_PATH" "$BACKUP_PATH"
fi

cat > "$HOOK_PATH" <<EOF
#!/usr/bin/env bash
set -euo pipefail
# BEGIN HERMES CRYPTO PRE-COMMIT
REPO_ROOT="$REPO_ROOT"
BACKUP_PATH="$BACKUP_PATH"
SCRIPT_PATH="$SCRIPT_PATH"

if [[ -x "\$BACKUP_PATH" ]]; then
  "\$BACKUP_PATH"
fi

exec "\$SCRIPT_PATH"
# END HERMES CRYPTO PRE-COMMIT
EOF

chmod +x "$HOOK_PATH"

echo "Installed crypto pre-commit hook at $HOOK_PATH"
echo "Versioned script: $SCRIPT_PATH"
if [[ -f "$BACKUP_PATH" ]]; then
  echo "Backup preserved: $BACKUP_PATH"
fi
