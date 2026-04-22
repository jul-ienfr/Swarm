#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

collect_pushed_files() {
  if [[ -n "${HERMES_PREPUSH_CHANGED_FILES:-}" ]]; then
    printf '%s\n' "$HERMES_PREPUSH_CHANGED_FILES"
    return 0
  fi

  local local_ref local_sha remote_ref remote_sha merge_base diff_range
  if ! read -r local_ref local_sha remote_ref remote_sha; then
    return 1
  fi

  if [[ -z "${local_sha:-}" ]]; then
    return 1
  fi

  if [[ "${remote_sha:-}" =~ ^0+$ ]]; then
    diff_range="$local_sha"
  else
    merge_base="$(git merge-base "$local_sha" "$remote_sha")"
    diff_range="$merge_base..$local_sha"
  fi

  git diff --name-only --diff-filter=ACMR "$diff_range"
}

should_run_crypto_gate() {
  local changed_files
  changed_files="$(collect_pushed_files || true)"

  if [[ -z "$changed_files" ]]; then
    return 1
  fi

  while IFS= read -r file; do
    case "$file" in
      subprojects/prediction/src/lib/prediction-markets/crypto/*|\
      subprojects/prediction/src/app/api/v1/prediction-markets/crypto/*|\
      subprojects/prediction/src/lib/__tests__/prediction-markets-crypto*|\
      subprojects/prediction/docs/CRYPTO.md|\
      subprojects/prediction/docs/CRYPTO-implementation-plan.md|\
      subprojects/prediction/CRYPTO_TEST_MATRIX.md|\
      subprojects/prediction/scripts/test-crypto.sh|\
      subprojects/prediction/scripts/pre-commit-crypto.sh|\
      subprojects/prediction/scripts/pre-push-crypto.sh|\
      subprojects/prediction/scripts/install-crypto-pre-commit.sh|\
      subprojects/prediction/scripts/install-crypto-pre-push.sh|\
      subprojects/prediction/package.json)
        return 0
        ;;
    esac
  done <<< "$changed_files"

  return 1
}

resolve_gate_level() {
  local branch_name
  branch_name="${HERMES_PREPUSH_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"

  if [[ -n "${HERMES_CRYPTO_PREPUSH_LEVEL:-}" ]]; then
    printf '%s\n' "$HERMES_CRYPTO_PREPUSH_LEVEL"
    return 0
  fi

  case "$branch_name" in
    main|master)
      printf 'merge\n'
      ;;
    *)
      printf 'safe\n'
      ;;
  esac
}

if ! should_run_crypto_gate; then
  echo "[crypto-pre-push] no pushed crypto changes -> skip"
  exit 0
fi

LEVEL="$(resolve_gate_level)"
case "$LEVEL" in
  safe)
    echo "[crypto-pre-push] crypto changes detected -> npm run test:crypto:safe"
    npm run test:crypto:safe
    ;;
  merge)
    echo "[crypto-pre-push] crypto changes detected on protected flow -> npm run test:crypto:merge"
    npm run test:crypto:merge
    ;;
  *)
    echo "[crypto-pre-push] invalid level: $LEVEL" >&2
    echo "Allowed values: safe, merge" >&2
    exit 1
    ;;
 esac
